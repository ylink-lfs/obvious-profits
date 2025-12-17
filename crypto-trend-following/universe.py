# universe.py
# Contract Universe Management - Discovers contracts and manages the trading universe

import os
import re
import json
import zipfile
import pandas as pd
from typing import Dict, List, Optional, Tuple


class ContractListingScanner:
    """
    Scans the data source to discover all contracts and their listing/delisting times.
    Results are cached to a JSON file for subsequent backtest runs.
    """
    
    def __init__(self, config):
        self.config = config
        self.futures_data_path = config['futures_data_path']
        self.cache_file = os.path.join(
            os.path.dirname(__file__), 
            config['listing_cache_file']
        )
        # symbol -> {"start_time": timestamp_ms, "end_time": timestamp_ms}
        self.listings: Dict[str, Dict[str, int]] = {}
        
    def scan_contracts(self, force_rescan: bool = False) -> Dict[str, Dict[str, int]]:
        """
        Scan all contracts in the data source and get their listing/delisting times.
        Uses cached results if available unless force_rescan is True.
        
        Returns:
            Dict mapping symbol to {"start_time": ms, "end_time": ms}
        """
        # Try to load from cache first
        if not force_rescan and os.path.exists(self.cache_file):
            print(f"[ContractScanner] Loading listings from cache: {self.cache_file}")
            with open(self.cache_file, 'r') as f:
                self.listings = json.load(f)
            print(f"[ContractScanner] Loaded {len(self.listings)} contracts from cache.")
            return self.listings
        
        print(f"[ContractScanner] Scanning contracts from: {self.futures_data_path}")
        
        if not os.path.exists(self.futures_data_path):
            print(f"[ContractScanner] ERROR: Path does not exist: {self.futures_data_path}")
            return {}
        
        # Iterate through all contract directories
        for symbol_dir in os.listdir(self.futures_data_path):
            symbol_path = os.path.join(self.futures_data_path, symbol_dir)
            if not os.path.isdir(symbol_path):
                continue
                
            # Look for 1m timeframe directory
            timeframe_path = os.path.join(symbol_path, '1m')
            if not os.path.exists(timeframe_path):
                continue
            
            # Find the listing and delisting times
            times = self._get_contract_time_range(symbol_dir, timeframe_path)
            if times:
                self.listings[symbol_dir] = {
                    "start_time": times[0],
                    "end_time": times[1]
                }
        
        # Save to cache
        print(f"[ContractScanner] Scanned {len(self.listings)} contracts. Saving to cache...")
        with open(self.cache_file, 'w') as f:
            json.dump(self.listings, f, indent=2)
        
        return self.listings
    
    def _extract_date_from_filename(self, filename: str) -> Optional[str]:
        """
        Extract date string from filename like 'GRTUSDT-1m-2021-01-01.zip'.
        Returns date string in format 'YYYY-MM-DD' for sorting.
        """
        # Match pattern: SYMBOL-TIMEFRAME-YYYY-MM-DD.zip
        match = re.search(r'-(\d{4}-\d{2}-\d{2})\.zip$', filename)
        if match:
            return match.group(1)
        return None
    
    def _sort_zip_files_by_date(self, zip_files: List[str]) -> List[str]:
        """
        Sort zip files by the date in their filename.
        Files without valid dates are placed at the end.
        """
        def get_sort_key(filename):
            date_str = self._extract_date_from_filename(filename)
            # Return tuple: (has_date, date_string)
            # Files with dates come first (False < True when negated)
            if date_str:
                return (0, date_str)
            return (1, filename)  # Fallback to filename for files without date
        
        return sorted(zip_files, key=get_sort_key)
    
    def _get_contract_time_range(self, symbol: str, timeframe_path: str) -> Optional[Tuple[int, int]]:
        """
        Get the listing and delisting time of a contract by reading the earliest 
        and latest data files.
        
        Returns:
            Tuple of (start_timestamp_ms, end_timestamp_ms), or None if unable to determine
        """
        try:
            # Find all zip files or date range folders
            items = os.listdir(timeframe_path)
            
            # Check for date range folder structure (e.g., "2021-01-01_2024-12-31")
            date_range_folders = [d for d in items if '_' in d and os.path.isdir(
                os.path.join(timeframe_path, d))]
            
            if date_range_folders:
                # Use the date range folder
                folder_path = os.path.join(timeframe_path, sorted(date_range_folders)[0])
                zip_files = [f for f in os.listdir(folder_path) if f.endswith('.zip')]
            else:
                # Direct zip files in timeframe folder
                zip_files = [f for f in items if f.endswith('.zip')]
                folder_path = timeframe_path
            
            if not zip_files:
                return None
            
            # Sort zip files by date in filename
            sorted_zips = self._sort_zip_files_by_date(zip_files)
            
            # Get the earliest and latest zip files
            earliest_zip = sorted_zips[0]
            latest_zip = sorted_zips[-1]
            
            earliest_zip_path = os.path.join(folder_path, earliest_zip)
            latest_zip_path = os.path.join(folder_path, latest_zip)
            
            # Read the first timestamp from earliest zip
            start_time = self._read_first_timestamp_from_zip(earliest_zip_path)
            
            # Read the last timestamp from latest zip
            end_time = self._read_last_timestamp_from_zip(latest_zip_path)
            
            if start_time and end_time:
                return (start_time, end_time)
            return None
            
        except Exception as e:
            print(f"[ContractScanner] Error scanning {symbol}: {e}")
            return None
    
    def _read_first_timestamp_from_zip(self, zip_path: str) -> Optional[int]:
        """
        Read the first timestamp from a zip file containing CSV data.
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Get the CSV file inside the zip
                csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                if not csv_files:
                    return None
                
                with zf.open(csv_files[0]) as csv_file:
                    # Read the first two lines to handle both header and headerless CSVs
                    df = pd.read_csv(csv_file, nrows=2, header=None)
                    if df.empty:
                        return None
                    
                    # First column is open_time (timestamp in ms)
                    # Check if the first row is a header (non-numeric value)
                    first_value = df.iloc[0, 0]
                    try:
                        timestamp = int(first_value)
                    except (ValueError, TypeError):
                        # First row is a header, use the second row
                        if len(df) < 2:
                            return None
                        timestamp = int(df.iloc[1, 0])
                    
                    # Handle microseconds if present (2025+ data)
                    if timestamp > 1e15:
                        timestamp = timestamp // 1000
                    
                    return timestamp
                    
        except Exception as e:
            print(f"[ContractScanner] Error reading zip {zip_path}: {e}")
            return None
    
    def _read_last_timestamp_from_zip(self, zip_path: str) -> Optional[int]:
        """
        Read the last timestamp from a zip file containing CSV data.
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Get the CSV file inside the zip
                csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                if not csv_files:
                    return None
                
                with zf.open(csv_files[0]) as csv_file:
                    # Read the entire file to get the last row
                    # First, check if there's a header
                    df = pd.read_csv(csv_file, nrows=1, header=None)
                    if df.empty:
                        return None
                    
                    # Check if first row is header
                    has_header = False
                    try:
                        int(df.iloc[0, 0])
                    except (ValueError, TypeError):
                        has_header = True
                
                # Re-read the file with proper header handling
                with zf.open(csv_files[0]) as csv_file:
                    if has_header:
                        df = pd.read_csv(csv_file)
                    else:
                        df = pd.read_csv(csv_file, header=None)
                    
                    if df.empty:
                        return None
                    
                    # Get the last row's first column (open_time)
                    timestamp = int(df.iloc[-1, 0])
                    
                    # Handle microseconds if present (2025+ data)
                    if timestamp > 1e15:
                        timestamp = timestamp // 1000
                    
                    return timestamp
                    
        except Exception as e:
            print(f"[ContractScanner] Error reading zip {zip_path}: {e}")
            return None


class UniverseFilter:
    """
    Filters the contract universe based on configurable rules.
    Implemented as pluggable filters for easy modification.
    """
    
    def __init__(self, config):
        self.config = config
        self.filters = []
        self._setup_default_filters()
    
    def _setup_default_filters(self):
        """Setup default filters from config."""
        # Non-USDT pair filter (must come first to filter out ETHBTC etc.)
        self.filters.append(
            USDTPairFilter(self.config.get('valid_quote_assets', ['USDT', 'BUSD', 'USDC']))
        )
        # Delivery/Quarterly contract filter (filter out BTCUSDT_210326 etc.)
        self.filters.append(
            DeliveryContractFilter()
        )
        # Settled contract filter (filter out AERGOUSDTSETTLED etc.)
        self.filters.append(
            SettledContractFilter()
        )
        # Non-crypto asset filter (filter out XAUUSDT etc.)
        self.filters.append(
            NonCryptoAssetFilter(self.config.get('excluded_non_crypto', ['XAU', 'XAG']))
        )
        # Stablecoin filter
        self.filters.append(
            StablecoinFilter(self.config['excluded_stablecoins'])
        )
        # Index contract filter
        self.filters.append(
            IndexFilter(self.config['excluded_indices'])
        )
        # Low volatility giants filter
        self.filters.append(
            GiantFilter(self.config['excluded_giants'])
        )
    
    def add_filter(self, filter_func):
        """Add a custom filter function."""
        self.filters.append(filter_func)
    
    def filter_universe(self, symbols: List[str]) -> List[str]:
        """
        Apply all filters to the symbol list.
        
        Args:
            symbols: List of symbol strings
            
        Returns:
            Filtered list of symbols
        """
        filtered = symbols.copy()
        for f in self.filters:
            before_count = len(filtered)
            filtered = f.filter(filtered)
            removed = before_count - len(filtered)
            if removed > 0:
                print(f"[UniverseFilter] {f.__class__.__name__} removed {removed} symbols")
        
        return filtered


class StablecoinFilter:
    """Filter out stablecoin contracts."""
    
    def __init__(self, excluded_tokens: List[str]):
        self.excluded = set(excluded_tokens)
    
    def filter(self, symbols: List[str]) -> List[str]:
        return [s for s in symbols if not self._is_stablecoin(s)]
    
    def _is_stablecoin(self, symbol: str) -> bool:
        base = self._get_base_symbol(symbol)
        return base in self.excluded or symbol in self.excluded
    
    def _get_base_symbol(self, symbol: str) -> str:
        """Extract base symbol using regex for robust parsing."""
        match = re.match(r'^(.*?)(USDT|BUSD|USDC)$', symbol)
        if match:
            return match.group(1)
        return symbol


class IndexFilter:
    """Filter out index contracts."""
    
    def __init__(self, excluded_indices: List[str]):
        self.excluded = set(excluded_indices)
    
    def filter(self, symbols: List[str]) -> List[str]:
        return [s for s in symbols if not self._is_index(s)]
    
    def _is_index(self, symbol: str) -> bool:
        base = self._get_base_symbol(symbol)
        return base in self.excluded
    
    def _get_base_symbol(self, symbol: str) -> str:
        """Extract base symbol using regex for robust parsing."""
        match = re.match(r'^(.*?)(USDT|BUSD|USDC)$', symbol)
        if match:
            return match.group(1)
        return symbol


class GiantFilter:
    """Filter out low volatility giants like BTC and ETH."""
    
    def __init__(self, excluded_giants: List[str]):
        self.excluded = set(excluded_giants)
    
    def filter(self, symbols: List[str]) -> List[str]:
        return [s for s in symbols if not self._is_giant(s)]
    
    def _is_giant(self, symbol: str) -> bool:
        base = self._get_base_symbol(symbol)
        return base in self.excluded
    
    def _get_base_symbol(self, symbol: str) -> str:
        """Extract base symbol using regex for robust parsing."""
        match = re.match(r'^(.*?)(USDT|BUSD|USDC)$', symbol)
        if match:
            return match.group(1)
        return symbol


class USDTPairFilter:
    """
    Filter to ensure only valid USDT/BUSD/USDC pairs are included.
    This filters out cross pairs like ETHBTC.
    """
    
    def __init__(self, valid_quotes: List[str]):
        self.valid_quotes = set(valid_quotes)
    
    def filter(self, symbols: List[str]) -> List[str]:
        return [s for s in symbols if self._is_valid_pair(s)]
    
    def _is_valid_pair(self, symbol: str) -> bool:
        """Check if the symbol ends with a valid quote asset."""
        for quote in self.valid_quotes:
            if symbol.endswith(quote):
                return True
        return False


class DeliveryContractFilter:
    """
    Filter out delivery/quarterly contracts.
    These have format like BTCUSDT_210326 (dated contracts).
    """
    
    def filter(self, symbols: List[str]) -> List[str]:
        return [s for s in symbols if not self._is_delivery(s)]
    
    def _is_delivery(self, symbol: str) -> bool:
        """Check if symbol is a delivery contract (contains _YYMMDD suffix)."""
        return bool(re.search(r'_\d{6}$', symbol))


class SettledContractFilter:
    """
    Filter out settled/delisted contracts.
    These have SETTLED suffix like AERGOUSDTSETTLED.
    """
    
    def filter(self, symbols: List[str]) -> List[str]:
        return [s for s in symbols if not self._is_settled(s)]
    
    def _is_settled(self, symbol: str) -> bool:
        """Check if symbol has SETTLED suffix."""
        return symbol.endswith('SETTLED')


class NonCryptoAssetFilter:
    """
    Filter out non-crypto assets like gold (XAU), silver (XAG).
    These traditional assets shouldn't be in a meme coin strategy.
    """
    
    def __init__(self, excluded_assets: List[str]):
        self.excluded = set(excluded_assets)
    
    def filter(self, symbols: List[str]) -> List[str]:
        return [s for s in symbols if not self._is_non_crypto(s)]
    
    def _is_non_crypto(self, symbol: str) -> bool:
        """Check if symbol contains a non-crypto asset identifier."""
        for asset in self.excluded:
            if asset in symbol:
                return True
        return False


class UniverseManager:
    """
    Manages the trading universe at any point in time during backtest.
    Combines contract listings with filters to provide available symbols.
    """
    
    def __init__(self, config):
        self.config = config
        self.scanner = ContractListingScanner(config)
        self.filter = UniverseFilter(config)
        self.listings: Dict[str, Dict[str, int]] = {}  # symbol -> {"start_time": ms, "end_time": ms}
    
    def initialize(self, force_rescan: bool = False):
        """Initialize by scanning contracts."""
        self.listings = self.scanner.scan_contracts(force_rescan)
        print(f"[UniverseManager] Initialized with {len(self.listings)} contracts")
    
    def get_available_contracts(self, current_time_ms: int) -> List[str]:
        """
        Get list of contracts available at a specific time.
        A contract is available if current_time is between its start_time and end_time.
        
        Args:
            current_time_ms: Current backtest time in milliseconds
            
        Returns:
            List of available symbol strings (after filtering)
        """
        # Get contracts that are active at current time
        # (listed before current time AND not yet delisted)
        available = [
            symbol for symbol, times in self.listings.items()
            if times["start_time"] <= current_time_ms <= times["end_time"]
        ]
        
        # Apply filters
        filtered = self.filter.filter_universe(available)
        
        return filtered
    
    def get_listing_time(self, symbol: str) -> Optional[int]:
        """Get the listing (start) time of a specific contract."""
        if symbol in self.listings:
            return self.listings[symbol]["start_time"]
        return None
    
    def get_delisting_time(self, symbol: str) -> Optional[int]:
        """Get the delisting (end) time of a specific contract."""
        if symbol in self.listings:
            return self.listings[symbol]["end_time"]
        return None
    
    def get_contract_time_range(self, symbol: str) -> Optional[Tuple[int, int]]:
        """Get the (start_time, end_time) tuple for a specific contract."""
        if symbol in self.listings:
            return (self.listings[symbol]["start_time"], self.listings[symbol]["end_time"])
        return None
