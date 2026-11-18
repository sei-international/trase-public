class ConservedValueError(Exception):
    pass


class LinkError(Exception):
    pass


class RowSplittingError(Exception):
    """An update would have split flows that the caller said it would not split.

    Raised by `DataFrameContainer.update` when `allow_splitting=False` and the
    dataframe repeats an existing "_id". See the `allow_splitting` argument of
    `trase.tools.sei_pcs.supply_chain.SupplyChain.update`.
    """
