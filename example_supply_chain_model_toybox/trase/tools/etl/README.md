# ETL tool

Loads raw input files into pandas, cleans them and writes them to a standard place
where the SEI-PCS engine can find them.

The ETL tool handles:

 - Reading raw files (CSV, Excel, Parquet, JSON) from the local disk
 - Selecting, renaming and type-casting columns, declared with `Column(...)`
 - Simple pre-processing such as filtering rows, in a `process(df)` method
 - Reporting row counts and column totals before and after each step
 - Writing the result into a standard directory layout:

```nohighlight
<model>/<year>/
├── downloaded/   # copy of the raw file, exactly as read
└── prepared/     # cleaned file, ready for SupplyChain.load()
```

See `trase/models/orvessa/candy/preparation.py` for a worked example.
