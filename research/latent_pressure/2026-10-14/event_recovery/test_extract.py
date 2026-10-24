"""Hermetic protocol tests; no market source read and no networking."""
import gzip,json,struct,subprocess,tempfile,unittest
from pathlib import Path
O=Path(__file__).parent
TS=1791216000123456789

def block(t,b):
 b+=b'\0'*((-len(b))%4);n=len(b)+12
 return struct.pack('<II',t,n)+b+struct.pack('<I',n)
def header(link=1):
 return block(0x0a0d0d0a,struct.pack('<IHHq',0x1a2b3c4d,1,0,-1))+block(1,struct.pack('<HHI',link,0,65535)+struct.pack('<HHB3x',9,1,6)+b'\0'*4)
def execution(ts=TS):return struct.pack('<BBQ8sQIqQ',ord('L'),0,ts,b'AAPL    ',2**60+3,123,4567890,2**61+5)
def packet(messages,seq=1,offset=0,proto=0x8005,frag=0,declared_delta=0):
 payload=b''.join(struct.pack('<H',len(m))+m for m in messages)
 tp=struct.pack('<BBHIIHHQQQ',1,0,proto,1,99,len(payload)+declared_delta,len(messages),offset,seq,TS+1000)+payload
 udp=struct.pack('!HHHH',1000,1000,8+len(tp),0)+tp
 ip=struct.pack('!BBHHHBBH4s4s',0x45,0,20+len(udp),0,frag,64,17,0,b'\1\2\3\4',b'\5\6\7\10')+udp
 eth=b'\0'*12+b'\x08\x00'+ip
 return block(6,struct.pack('<IIIII',0,1,3,len(eth),len(eth))+eth)

class TestExtractor(unittest.TestCase):
 def call(self,data,ok=True,limit=None):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'fixture.gz';p.write_bytes(gzip.compress(data));out=root/'out'
   r=subprocess.run([str(O/'extract_dpls'),str(p),str(out)]+([str(limit)] if limit is not None else []),capture_output=True,text=True)
   if ok:
    self.assertEqual(r.returncode,0,r.stderr);s=json.loads((out/'scan.json').read_text());txt=gzip.decompress((out/'executions.csv.gz').read_bytes()).decode();return s,txt,(out/'selected_messages.bin').read_bytes()
   self.assertNotEqual(r.returncode,0);self.assertFalse((out/'scan.json').exists());return r.stderr
 def test_lossless_integers(self):
  s,t,b=self.call(header()+packet([execution()]));self.assertEqual(s['executions'],1);self.assertIn(str(TS),t);self.assertIn(str(2**60+3),t);self.assertEqual(b[:8],b'DPLSRAW1');self.assertEqual(struct.unpack_from('<Q',b,8)[0],1)
 def test_continuous(self):
  s,_,_=self.call(header()+packet([execution()])+packet([execution(TS+1)],2,48));self.assertEqual(s['messages'],2)
 def test_full_duplicate_ignored(self):
  s,_,_=self.call(header()+packet([execution()])*2);self.assertEqual(s['executions'],1);self.assertEqual(s['streams'][0]['duplicate_messages'],1)
 def test_sequence_gap_fails(self):self.assertIn('sequence gap',self.call(header()+packet([execution()])+packet([execution()],3,48),False))
 def test_offset_gap_fails(self):self.assertIn('offset',self.call(header()+packet([execution()])+packet([execution()],2,49),False))
 def test_wrong_protocol(self):self.assertIn('protocol',self.call(header()+packet([execution()],proto=0x8004),False))
 def test_fragment(self):self.assertIn('fragments',self.call(header()+packet([execution()],frag=0x2000),False))
 def test_payload_mismatch(self):self.assertIn('payload length',self.call(header()+packet([execution()],declared_delta=1),False))
 def test_short_execution(self):self.assertIn('short Order',self.call(header()+packet([execution()[:-1]]),False))
 def test_unknown_message_preserved(self):
  m=bytes([ord('z'),0])+struct.pack('<Q',TS)+b'AAPL    '+b'12345678';s,t,b=self.call(header()+packet([m]));self.assertEqual(s['selected_messages'],1);self.assertEqual(s['executions'],0)
 def test_bad_link(self):self.assertIn('linktype',self.call(header(113)+packet([execution()]),False))
 def test_truncated_packet(self):self.assertIn('truncated',self.call((header()+packet([execution()]))[:-6],False))
 def test_heartbeat(self):
  s,_,_=self.call(header()+packet([],seq=1)+packet([execution()]));self.assertEqual(s['messages'],1)
 def test_negative_price(self):
  m=bytearray(execution());struct.pack_into('<q',m,30,-1);self.assertIn('invalid execution',self.call(header()+packet([bytes(m)]),False))
 def test_event_after_send(self):
  self.assertIn('invalid execution',self.call(header()+packet([execution(TS+2000)]),False))
 def test_udp_must_fit_declared_ipv4(self):
  b=bytearray(packet([execution()]));ip=8+20+14;old=struct.unpack_from('!H',b,ip+2)[0];struct.pack_into('!H',b,ip+2,old-1)
  self.assertIn('UDP length',self.call(header()+bytes(b),False))
 def test_json_safe_unknown_types(self):
  for typ in [0,34,92,255]:
   m=bytearray(execution());m[0]=typ;s,_,_=self.call(header()+packet([bytes(m)]));self.assertEqual(s['selected_messages'],1)
 def test_packet_limit_applies_to_heartbeats(self):
  s,_,_=self.call(header()+packet([])*5+packet([execution()]),limit=3);self.assertEqual(s['packets'],3);self.assertFalse(s['complete_archive'])
 def test_growth_tolerated(self):
  s,_,_=self.call(header()+packet([execution()+b'extra']));self.assertEqual(s['executions'],1)
if __name__=='__main__':unittest.main(verbosity=2)
