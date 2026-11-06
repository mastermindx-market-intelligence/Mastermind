# IEX event-level latent-pressure research

Read `REPORT.md` and `QUALIFICATION.json`. The full existing archive's framing and selected displayed-execution fields were checked. The real execution-history candidate failed its positive gate. The stronger recovery engine is tested on synthetic normalized events and deliberately refuses an unqualified DEEP+ book adapter.

## Files

`extract_dpls.cpp` scans gzip/PCAPNG/Ethernet/IPv4/UDP/IEX-TP and decodes selected L fields. Other selected messages are retained raw only. `event_study.py` runs the frozen execution-history comparison and an independent raw-L parser. `research_snapshot.py` produces historical, read-only observations without forecast/trading authority. `book_recovery.py` implements the synthetic recovery/censoring engine. `test_extract.py`, `test_event_study.py` and `test_recovery.py` contain focused tests.

`PROTOCOL.json`, `TRANSPORT_SCAN.json`, `EVENT_STUDY_RESULTS.json`, `DEPENDENCE_QUALIFICATION.json`, `QUALIFICATION.json`, and the private-evidence hashes retain the scientific identities. Example records distinguish real historical execution observations from constructed recovery examples. Neither is a validated signal.

## Reproduce locally using authorized inputs

C++17, zlib, Python 3, NumPy, pandas and SciPy are required. The scanner supports the observed little-endian PCAPNG/Ethernet/IPv4/unfragmented-UDP/IEX-TP0x8005 path; unsupported formats fail rather than being silently reinterpreted. New output directories are mandatory. These commands do not download market data or change production.

```sh
clang++ -O3 -std=c++17 extract_dpls.cpp -lz -o extract_dpls
python3 test_extract.py
python3 test_recovery.py
python3 test_event_study.py
./extract_dpls /authorized/20261005_IEXTP1_DPLS1.0.pcap.gz /new/scan-directory
python3 event_study.py --scan /new/scan-directory --out /new/study-directory
python3 research_snapshot.py --executions /new/scan-directory/executions.csv.gz --at 2026-10-05T14:00:00-04:00
```

The study and consumer intentionally bind the recorded October 5 research protocol/date. A different day or data/feature policy is a new experiment, not an exact replay. The recorded original archive hash must match. Original full-scan and repaired malformed-input code revisions are distinguished in the qualification evidence.

Do not repeat an accepted full scan merely to refresh timestamps. Existing exact source/output hashes and independent reference parsing may be reused. Do not publish private capture, extracted-message or per-forecast series accidentally. `private/` is ignored.

Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data Terms of Use: https://www.iex.io/legal/hist-data-terms
