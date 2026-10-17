// Research-only IEX HIST PCAPNG / IEX-TP scanner. Original implementation.
// Interprets only documented Order Executed (L) fields from DEEP+ p24.
// Retains selected raw messages separately for future qualified book replay.
#include <zlib.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
uint16_t u16(const unsigned char*p){return uint16_t(p[0])|(uint16_t(p[1])<<8);}
uint32_t u32(const unsigned char*p){return uint32_t(u16(p))|(uint32_t(u16(p+2))<<16);}
uint64_t u64(const unsigned char*p){return uint64_t(u32(p))|(uint64_t(u32(p+4))<<32);}
string json_byte_key(int k){if(k>=32&&k<=126&&k!=34&&k!=92)return string(1,char(k));char b[7];snprintf(b,7,"\\u%04x",k);return string(b);}
void write_le(ostream&out,uint64_t v,unsigned n){unsigned char b[8];for(unsigned i=0;i<n;i++)b[i]=(v>>(8*i))&255;out.write((char*)b,n);}
uint16_t be16(const unsigned char*p){return (uint16_t(p[0])<<8)|p[1];}
struct Reader{gzFile f;uint64_t bytes=0;explicit Reader(const char*p){f=gzopen(p,"rb");if(!f)throw runtime_error("input open");gzbuffer(f,4<<20);}~Reader(){gzclose(f);}bool read(void*p,size_t n,bool eof=false){size_t got=0;while(got<n){int k=gzread(f,(char*)p+got,n-got);if(k<0){int e;throw runtime_error(gzerror(f,&e));}if(!k){if(eof&&!got&&gzeof(f))return false;throw runtime_error("truncated input");}got+=k;}bytes+=n;return true;}};
struct Stream{uint64_t next=0,offset=0,first=0,last=0,packets=0,msgs=0,gaps=0,duplicates=0,overlaps=0,offset_errors=0,lastsend=0,send_backwards=0;};
int main(int argc,char**argv){try{
 if(argc<3||argc>4)throw runtime_error("usage: extract_dpls INPUT.pcap.gz NEW_OUTPUT_DIRECTORY [packet_limit]");
 filesystem::path out=argv[2];if(filesystem::exists(out))throw runtime_error("output exists: no overwrite");filesystem::create_directory(out);
 uint64_t limit=argc==4?stoull(argv[3]):0, packets=0, nonudp=0, fragments=0, messages=0, selected=0, executions=0, unknown_blocks=0, sections=0;
 array<string,8> names={"AAPL","MSFT","NVDA","AMD","MU","INTC","SPY","XLV"};map<string,int> wanted;for(int i=0;i<8;i++)wanted[names[i]]=i;
 ofstream raw(out/"selected_messages.bin",ios::binary);raw.write("DPLSRAW1",8);
 gzFile csv=gzopen((out/"executions.csv.gz").c_str(),"wb1");if(!csv)throw runtime_error("output open");gzbuffer(csv,1<<20);
 gzputs(csv,"ticker,timestamp_ns,sequence,send_ns,capture_ticks,channel,session,order_id,size,price_1e4,trade_id,sale_flags\n");
 map<pair<uint32_t,uint32_t>,Stream> streams;map<int,uint64_t> kinds,flags;map<string,uint64_t> byname;vector<int> links;vector<unsigned> resolutions;
 Reader f(argv[1]);unsigned char h[8];bool full=false;
 while(true){
  if(limit&&packets>=limit)break;
  if(!f.read(h,8,true)){full=true;break;}
  uint32_t type=u32(h),n=u32(h+4);if(n<12||n>(16u<<20)||n%4)throw runtime_error("invalid PCAPNG block length");vector<unsigned char>b(n-8);f.read(b.data(),b.size());if(u32(b.data()+b.size()-4)!=n)throw runtime_error("PCAPNG trailer mismatch");
  if(type==0x0a0d0d0a){if(u32(b.data())!=0x1a2b3c4d)throw runtime_error("unsupported PCAPNG endianness");links.clear();resolutions.clear();sections++;continue;}
  if(type==1){if(b.size()<12)throw runtime_error("short IDB");links.push_back(u16(b.data()));unsigned res=6;for(size_t z=8;z+4<=b.size()-4;){auto code=u16(&b[z]),len=u16(&b[z+2]);z+=4;if(z+len>b.size()-4)throw runtime_error("bad IDB option");if(code==9&&len==1)res=b[z];if(!code)break;z+=(len+3)&~3u;}resolutions.push_back(res);continue;}
  if(type!=6){unknown_blocks++;continue;}
  if(b.size()<24)throw runtime_error("short EPB");uint32_t iface=u32(b.data()),cap=u32(&b[12]),orig=u32(&b[16]);if(iface>=links.size()||links[iface]!=1)throw runtime_error("unsupported interface/linktype");if(cap!=orig||cap+24>b.size())throw runtime_error("truncated captured packet");
  const unsigned char*e=&b[20];uint64_t capture=(uint64_t(u32(&b[4]))<<32)|u32(&b[8]);packets++;
  size_t ip=14;if(cap<14)throw runtime_error("short ethernet");uint16_t et=be16(e+12);while(et==0x8100||et==0x88a8){if(cap<ip+4)throw runtime_error("short vlan");et=be16(e+ip+2);ip+=4;}
  if(et!=0x0800||cap<ip+20||e[ip+9]!=17){nonudp++;continue;}
  size_t ihl=(e[ip]&15)*4;uint16_t iplen=be16(e+ip+2);if((e[ip]>>4)!=4||ihl<20||cap<ip+iplen||iplen<ihl+8)throw runtime_error("invalid IPv4 length");
  if(be16(e+ip+6)&0x3fff){fragments++;throw runtime_error("IP fragments unsupported");}size_t udp=ip+ihl;auto udplen=be16(e+udp+4);if(udplen<48||udp+udplen>cap||udplen!=iplen-ihl)throw runtime_error("invalid UDP length");auto t=e+udp+8;size_t tn=udplen-8;
  if(t[0]!=1||u16(t+2)!=0x8005)throw runtime_error("wrong IEX-TP protocol");auto ch=u32(t+4),sess=u32(t+8);auto pl=u16(t+12),cnt=u16(t+14);auto off=u64(t+16),seq=u64(t+24),send=u64(t+32);if(tn!=40u+pl)throw runtime_error("IEX payload length mismatch");
  auto&st=streams[{ch,sess}];st.packets++;if(send<st.lastsend)st.send_backwards++;st.lastsend=send;
  if(!cnt)continue;if(!st.next){st.first=seq;st.next=seq;st.offset=off;}
  if(seq<st.next){if(seq+cnt<=st.next){st.duplicates+=cnt;continue;}st.overlaps++;throw runtime_error("partially overlapping packet");}
  if(seq!=st.next){st.gaps+=seq-st.next;throw runtime_error("sequence gap before stream repair");}
  if(off!=st.offset){st.offset_errors++;throw runtime_error("stream offset discontinuity");}
  size_t pos=40;
  for(unsigned j=0;j<cnt;j++){
   if(pos+2>tn)throw runtime_error("short message prefix");auto len=u16(t+pos);pos+=2;if(!len||pos+len>tn)throw runtime_error("bad message length");auto m=t+pos;pos+=len;messages++;kinds[m[0]]++;st.msgs++;
   if(len<18)continue;string sym((char*)m+10,8);while(!sym.empty()&&sym.back()==' ')sym.pop_back();auto it=wanted.find(sym);if(it==wanted.end())continue;selected++;byname[sym]++;
   // Raw source bytes; no inference of order side/modify semantics here.
   write_le(raw,seq+j,8);write_le(raw,send,8);write_le(raw,capture,8);write_le(raw,ch,4);write_le(raw,sess,4);write_le(raw,len,2);raw.write((char*)m,len);
   if(m[0]=='L'){
    if(len<46)throw runtime_error("short Order Executed");auto ts=u64(m+2),oid=u64(m+18),price=u64(m+30),tid=u64(m+38);auto qty=u32(m+26);if(!qty||!price||price>uint64_t(INT64_MAX)||ts>send)throw runtime_error("invalid execution");flags[m[1]]++;
    gzprintf(csv,"%s,%llu,%llu,%llu,%llu,%u,%u,%llu,%u,%llu,%llu,%u\n",sym.c_str(),(unsigned long long)ts,(unsigned long long)(seq+j),(unsigned long long)send,(unsigned long long)capture,ch,sess,(unsigned long long)oid,qty,(unsigned long long)price,(unsigned long long)tid,m[1]);executions++;
   }
  }
  if(pos!=tn)throw runtime_error("unconsumed message payload");st.next=seq+cnt;st.last=st.next-1;st.offset=off+pl;
  if(packets%5000000==0)cerr<<"PROGRESS packets="<<packets<<" messages="<<messages<<" selected="<<selected<<" executions="<<executions<<" uncompressed_bytes="<<f.bytes<<"\n";
  if(limit&&packets>=limit)break;
 }
 int zrc=gzclose(csv);if(zrc!=Z_OK)throw runtime_error("output compression failure");raw.close();if(!raw)throw runtime_error("output write error");
 ofstream q(out/"scan.json");if(!q)throw runtime_error("scan report open failed");q<<"{\"complete_archive\":"<<(full?"true":"false")<<",\"packets\":"<<packets<<",\"messages\":"<<messages<<",\"selected_messages\":"<<selected<<",\"executions\":"<<executions<<",\"uncompressed_bytes\":"<<f.bytes<<",\"sections\":"<<sections<<",\"other_blocks\":"<<unknown_blocks<<",\"non_udp\":"<<nonudp<<",\"fragments\":"<<fragments<<",\"streams\":[";bool first=true;
 for(auto&[key,st]:streams){if(!first)q<<",";first=false;q<<"{\"channel\":"<<key.first<<",\"session\":"<<key.second<<",\"first\":"<<st.first<<",\"last\":"<<st.last<<",\"messages\":"<<st.msgs<<",\"gaps\":"<<st.gaps<<",\"duplicate_messages\":"<<st.duplicates<<",\"send_time_backsteps\":"<<st.send_backwards<<"}";}
 q<<"],\"type_counts\":{";first=true;for(auto[k,v]:kinds){if(!first)q<<",";first=false;q<<"\""<<json_byte_key(k)<<"\":"<<v;}q<<"},\"selected_by_ticker\":{";first=true;for(auto&[k,v]:byname){if(!first)q<<",";first=false;q<<"\""<<k<<"\":"<<v;}q<<"},\"execution_flags\":{";first=true;for(auto[k,v]:flags){if(!first)q<<",";first=false;q<<"\""<<k<<"\":"<<v;}q<<"},\"interface_timestamp_resolutions\":[";first=true;for(auto x:resolutions){if(!first)q<<",";first=false;q<<x;}q<<"]}\n";q.close();if(!q)throw runtime_error("scan report write failed");cout<<"DONE packets="<<packets<<" messages="<<messages<<" executions="<<executions<<" full="<<full<<"\n";return 0;
}catch(const exception&e){cerr<<"FAIL "<<e.what()<<"\n";return 2;}}
