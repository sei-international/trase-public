from pathlib import Path

import pandas as pd

from trase.models.orvessa.candy.preparation import Municipalities
from trase.tools.sei_pcs.pandas_utilities import assert_frame_like
from trase.tools.sei_pcs.supply_chain import SupplyChain

EXPECTED = Path(__file__).parent / "data" / "ORVESSA_2017.csv"


def test_orvessa_end_to_end():
    expected = pd.read_csv(EXPECTED, sep=";", dtype=str)

    supplychain = SupplyChain("orvessa/candy", 2017)
    supplychain.preparation()
    supplychain.load()
    supplychain.run()
    supplychain.quality_assurance()
    supplychain.export_results()

    actual = pd.read_csv(supplychain.results_path, sep=";", dtype=str)
    assert_frame_like(actual, expected)

    # export also works without re-running preparation
    supplychain = SupplyChain("orvessa/candy", 2017)
    supplychain.load()
    supplychain.run()
    supplychain.export_results()


def test_preparation_classes_have_source_code():
    assert "class Municipalities" in Municipalities._source
