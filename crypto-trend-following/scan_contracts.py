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
        # Show sample of earliest and latest contracts
        import pandas as pd
        
        sorted_listings = sorted(listings.items(), key=lambda x: x[1])
        
        print("\n--- Earliest Listed Contracts ---")
        for symbol, ts in sorted_listings[:10]:
            dt = pd.to_datetime(ts, unit='ms')
            print(f"  {symbol}: {dt}")
        
        print("\n--- Latest Listed Contracts ---")
        for symbol, ts in sorted_listings[-10:]:
            dt = pd.to_datetime(ts, unit='ms')
            print(f"  {symbol}: {dt}")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
