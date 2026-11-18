"""Run the Orvessa toy supply-chain model from start to finish.

Usage:
    python run_orvessa.py

Outputs are written to trase/models/orvessa/candy/2017/ (see docs/reading-the-results.md).
"""

from trase.tools.sei_pcs.supply_chain import SupplyChain

YEAR = 2017


def main():
    # Point the engine at trase/models/orvessa/candy/definition.py
    sc = SupplyChain("orvessa/candy", YEAR)

    sc.preparation()  # 1. clean raw CSVs in data/ -> 2017/prepared/
    sc.load()  # 2. load prepared files, check types and links
    sc.run()  # 3. model.py: decision tree -> LP -> domestic demand -> deforestation
    sc.quality_assurance()  # 4. quality_assurance.py: sanity checks on the results

    print("\nVolume (tonnes) by status and decision-tree branch:")
    sc.flow_report_by_attribute("vol", ["status", "branch"])

    print("\nDeforestation (ha) by destination country:")
    sc.flow_report_by_attribute("deforestation", ["country"])

    sc.export_results()  # 5. write 2017/results/results.csv
    print(f"\nResults written to {sc.results_path}")


if __name__ == "__main__":
    main()
