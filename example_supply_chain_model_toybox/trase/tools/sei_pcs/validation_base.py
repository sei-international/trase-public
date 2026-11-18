from abc import ABC, abstractmethod

import pandas as pd


class Validation(ABC):
    @abstractmethod
    def is_valid(self, values: pd.Series) -> pd.Series:
        """Takes a Pandas Series of values and returns a boolean Pandas Series"""
        pass
