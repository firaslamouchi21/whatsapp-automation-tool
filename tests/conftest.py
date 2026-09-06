from pathlib import Path
from typing import Generator

import pandas as pd
import pytest


@pytest.fixture
def sample_leads_csv(tmp_path: Path) -> Generator[Path, None, None]:
    csv_file = tmp_path / "test_leads.csv"

    data = {
        "Business Name": ["Test Business 1", "Test Business 2", "Test Business 3"],
        "Phone Number": ["+97431691362", "+97450885757", "+97471722850"],
        "Category": ["Restaurant", "Cafe", "Retail"],
    }

    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False)

    yield csv_file


@pytest.fixture
def invalid_leads_csv(tmp_path: Path) -> Generator[Path, None, None]:
    csv_file = tmp_path / "invalid_leads.csv"

    data = {
        "Business Name": ["Invalid Business 1", "Invalid Business 2"],
        "Phone Number": ["invalid", "123"],
        "Category": ["Test", "Test"],
    }

    df = pd.DataFrame(data)
    df.to_csv(csv_file, index=False)

    yield csv_file
