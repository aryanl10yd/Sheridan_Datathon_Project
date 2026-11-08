# Backend

```bash
pip install -r requirements.txt
PYTHONPATH=src uvicorn spaceweather.main:app --reload
```

Set `SPACEWEATHER_DATASET` to an alternate CSV path and `HARDWARE_TOKEN` for the
authenticated hardware reset endpoint. The CSV must contain `datetime_utc`,
`bz_gsm_nT`, and `sym_h_nT`.
