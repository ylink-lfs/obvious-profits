# scan_contracts.py
# Standalone script to scan and cache contract listing times
# Run this before backtesting to build the contract universe cache

import argparse
from config import CONFIG
from universe import ContractListingScanner


def main():
    """Scan contracts and build listing time cache."""
    parser = argparse.ArgumentParser(
        description='Scan contract listing times from data source'
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force rescan even if cache exists'
    )
    parser.add_argument(
        '--data-path', '-d',
        type=str,
        help='Override futures data path from config'
    )
    
    args = parser.parse_args()
    
    # Update config if data path provided
    config = CONFIG.copy()
    if args.data_path:
        config['futures_data_path'] = args.data_path
    
    print("=" * 60)
    print("  CONTRACT LISTING SCANNER")
    print("=" * 60)
    print(f"\nData Path: {config['futures_data_path']}")
    print(f"Cache File: {config['listing_cache_file']}")
    print(f"Force Rescan: {args.force}")
    
    # Run scanner
    scanner = ContractListingScanner(config)
    listings = scanner.scan_contracts(force_rescan=args.force)
    
    # Print summary
    print("\n" + "=" * 60)
    print("  SCAN RESULTS")
    print("=" * 60)
    print(f"\nTotal Contracts Found: {len(listings)}")
    
    if listings:
        # Show sample of earliest and latest contracts by start time
        import pandas as pd
        
        sorted_by_start = sorted(listings.items(), key=lambda x: x[1]["start_time"])
        
        print("\n--- Earliest Listed Contracts (by start time) ---")
        for symbol, times in sorted_by_start[:10]:
            start_dt = pd.to_datetime(times["start_time"], unit='ms')
            end_dt = pd.to_datetime(times["end_time"], unit='ms')
            print(f"  {symbol}: {start_dt} -> {end_dt}")
        
        print("\n--- Latest Listed Contracts (by start time) ---")
        for symbol, times in sorted_by_start[-10:]:
            start_dt = pd.to_datetime(times["start_time"], unit='ms')
            end_dt = pd.to_datetime(times["end_time"], unit='ms')
            print(f"  {symbol}: {start_dt} -> {end_dt}")
        
        # Also show contracts sorted by end time (recently delisted)
        sorted_by_end = sorted(listings.items(), key=lambda x: x[1]["end_time"])
        
        print("\n--- Earliest Delisted Contracts (by end time) ---")
        for symbol, times in sorted_by_end[:10]:
            start_dt = pd.to_datetime(times["start_time"], unit='ms')
            end_dt = pd.to_datetime(times["end_time"], unit='ms')
            print(f"  {symbol}: {start_dt} -> {end_dt}")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
