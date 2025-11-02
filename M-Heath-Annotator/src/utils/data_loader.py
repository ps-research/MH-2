"""
Excel data loader for mental health annotation system.
Replaces Google Sheets with local Excel file support.
"""
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional
import logging


logger = logging.getLogger(__name__)


class ExcelDataLoader:
    """
    Loads mental health dataset from local Excel file.

    Replaces the original Google Sheets-based data loading with
    local Excel file support using pandas.
    """

    def __init__(self, excel_path: str, id_column: str = "ID", text_column: str = "Text"):
        """
        Initialize Excel data loader.

        Args:
            excel_path: Path to Excel file
            id_column: Name of ID column
            text_column: Name of text column
        """
        self.excel_path = Path(excel_path)
        self.id_column = id_column
        self.text_column = text_column

        if not self.excel_path.exists():
            raise FileNotFoundError(f"Excel file not found: {self.excel_path}")

        logger.info(f"ExcelDataLoader initialized with file: {self.excel_path}")

    def load_sheet(self, sheet_name: str) -> pd.DataFrame:
        """
        Load a single sheet from Excel file.

        Args:
            sheet_name: Name of sheet to load (Train, Validation, or Test)

        Returns:
            DataFrame with sheet data
        """
        try:
            df = pd.read_excel(self.excel_path, sheet_name=sheet_name)
            logger.info(f"Loaded {len(df)} samples from sheet '{sheet_name}'")

            # Validate required columns
            if self.id_column not in df.columns:
                raise ValueError(f"Sheet '{sheet_name}' missing required column: {self.id_column}")
            if self.text_column not in df.columns:
                raise ValueError(f"Sheet '{sheet_name}' missing required column: {self.text_column}")

            return df

        except Exception as e:
            logger.error(f"Error loading sheet '{sheet_name}': {e}")
            raise

    def load_all_sheets(self, sheet_names: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Load and combine multiple sheets from Excel file.

        Args:
            sheet_names: List of sheet names to load. If None, loads Train, Validation, Test

        Returns:
            Combined DataFrame with all samples
        """
        if sheet_names is None:
            sheet_names = ["Train", "Validation", "Test"]

        all_dfs = []

        for sheet_name in sheet_names:
            try:
                df = self.load_sheet(sheet_name)
                df['split'] = sheet_name  # Add split column to track source
                all_dfs.append(df)
            except Exception as e:
                logger.warning(f"Skipping sheet '{sheet_name}': {e}")
                continue

        if not all_dfs:
            raise ValueError("No sheets could be loaded successfully")

        combined_df = pd.concat(all_dfs, ignore_index=True)

        logger.info(f"Combined {len(combined_df)} total samples from {len(all_dfs)} sheets")

        return combined_df

    def get_sample_by_id(self, sample_id: str, sheet_names: Optional[List[str]] = None) -> Optional[Dict]:
        """
        Get a single sample by ID.

        Args:
            sample_id: Sample ID to retrieve
            sheet_names: Sheets to search

        Returns:
            Dictionary with sample data or None if not found
        """
        df = self.load_all_sheets(sheet_names)

        sample = df[df[self.id_column] == sample_id]

        if len(sample) == 0:
            logger.warning(f"Sample ID '{sample_id}' not found")
            return None

        if len(sample) > 1:
            logger.warning(f"Multiple samples found for ID '{sample_id}', returning first")

        return sample.iloc[0].to_dict()

    def get_all_sample_ids(self, sheet_names: Optional[List[str]] = None) -> List[str]:
        """
        Get list of all sample IDs.

        Args:
            sheet_names: Sheets to load

        Returns:
            List of sample IDs
        """
        df = self.load_all_sheets(sheet_names)
        return df[self.id_column].tolist()

    def get_samples_by_split(self, split: str = "Train") -> pd.DataFrame:
        """
        Get samples from a specific split.

        Args:
            split: Split name (Train, Validation, or Test)

        Returns:
            DataFrame with samples from specified split
        """
        df = self.load_all_sheets()
        return df[df['split'] == split].copy()

    def get_sample_count(self, sheet_names: Optional[List[str]] = None) -> int:
        """
        Get total number of samples.

        Args:
            sheet_names: Sheets to count

        Returns:
            Total sample count
        """
        df = self.load_all_sheets(sheet_names)
        return len(df)

    def validate_dataset(self) -> Dict[str, any]:
        """
        Validate dataset structure and content.

        Returns:
            Dictionary with validation results
        """
        validation = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'stats': {}
        }

        try:
            df = self.load_all_sheets()

            # Check for duplicates
            duplicate_ids = df[df[self.id_column].duplicated()]
            if len(duplicate_ids) > 0:
                validation['warnings'].append(f"Found {len(duplicate_ids)} duplicate IDs")

            # Check for missing values
            missing_ids = df[self.id_column].isnull().sum()
            missing_text = df[self.text_column].isnull().sum()

            if missing_ids > 0:
                validation['errors'].append(f"Found {missing_ids} missing IDs")
                validation['valid'] = False

            if missing_text > 0:
                validation['warnings'].append(f"Found {missing_text} missing text values")

            # Statistics
            validation['stats'] = {
                'total_samples': len(df),
                'unique_ids': df[self.id_column].nunique(),
                'by_split': df['split'].value_counts().to_dict(),
                'avg_text_length': df[self.text_column].str.len().mean(),
                'min_text_length': df[self.text_column].str.len().min(),
                'max_text_length': df[self.text_column].str.len().max()
            }

        except Exception as e:
            validation['valid'] = False
            validation['errors'].append(str(e))

        return validation


# ═══════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════

def load_dataset_from_config(config: dict) -> ExcelDataLoader:
    """
    Create ExcelDataLoader from configuration dictionary.

    Args:
        config: Configuration dict with 'data' section

    Returns:
        ExcelDataLoader instance
    """
    data_config = config.get('data', {})

    excel_path = data_config.get('excel_path', 'data/mhelp_dataset.xlsx')
    id_column = data_config.get('id_column', 'ID')
    text_column = data_config.get('text_column', 'Text')

    return ExcelDataLoader(excel_path, id_column, text_column)


def create_sample_excel_template(output_path: str = "data/mhelp_dataset_template.xlsx"):
    """
    Create a sample Excel template with correct structure.

    Args:
        output_path: Path where template will be saved
    """
    # Create sample data
    sample_data = {
        'ID': ['SAMPLE-001', 'SAMPLE-002', 'SAMPLE-003'],
        'Text': [
            'I have been feeling anxious about my exams lately.',
            'I cannot sleep and feel worried all the time.',
            'I need help managing my stress levels.'
        ]
    }

    df = pd.DataFrame(sample_data)

    # Create Excel writer
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Train', index=False)
        df.to_excel(writer, sheet_name='Validation', index=False)
        df.to_excel(writer, sheet_name='Test', index=False)

    logger.info(f"Created sample Excel template at: {output_path}")
    return output_path


# ═══════════════════════════════════════════════════════════
# EXAMPLE USAGE
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Example: Load dataset
    loader = ExcelDataLoader("data/mhelp_dataset.xlsx")

    # Load all data
    df = loader.load_all_sheets()
    print(f"Loaded {len(df)} samples")

    # Get specific sample
    sample = loader.get_sample_by_id("ID-123")
    if sample:
        print(f"Sample text: {sample['Text'][:100]}...")

    # Validate dataset
    validation = loader.validate_dataset()
    print(f"Dataset valid: {validation['valid']}")
    print(f"Statistics: {validation['stats']}")
