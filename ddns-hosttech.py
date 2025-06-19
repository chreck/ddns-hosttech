#!/usr/bin/env python3
# Documentation at https://www.hosttech.ch/blog/neue-api/
# and https://api.ns1.hosttech.eu/api/documentation/#/

__version__ = "1.0.1"

import json
import time
import logging
import os
import sys
from typing import List, Dict, Any, Optional
from requests import Response, get, post, put, delete, auth
from argparse import ArgumentParser
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ddns-hosttech')


class BearerAuth(auth.AuthBase):
    """Authentication class for Bearer token authorization"""
    
    def __init__(self, token: str):
        self.token = token

    def __call__(self, r):
        r.headers["authorization"] = "Bearer " + self.token
        return r


class HosttechApi:
    """Class to handle Hosttech DNS API operations"""
    
    def __init__(self, token: str, domains: List[str]):
        """Initialize the Hosttech API client
        
        Args:
            token: API authentication token
            domains: List of domains to update
        """
        self.token = token
        self.domains = domains
        self.api_base_url = "https://api.ns1.hosttech.eu"
        
    def get_current_ip(self, ipv4: bool = True) -> str:
        """Get the current public IP address
        
        Args:
            ipv4: Whether to get the IPv4 address (default: True)
        
        Returns:
            Current public IP address as string
            
        Raises:
            Exception: If IP address cannot be retrieved
        """
        try:
            response: Response = get("https://checkip.amazonaws.com" if ipv4 else "https://ifconfig.me/ip")
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
            
            # Remove any zone-id suffix ("%eth0") for IPv6 and trailing whitespace/newlines
            ip = response.text.split('%')[0].strip()
            logger.info(f"Current IP address: {ip}")
            return ip
        except Exception as e:
            logger.error(f"Could not get current IP address: {e}")
            raise Exception(f"Could not get current IP address: {e}")
    
    def get_zone_id(self, domain: str) -> int:
        """Get the zone ID for a domain
        
        Args:
            domain: Domain name to get zone ID for
            
        Returns:
            Zone ID as integer
            
        Raises:
            Exception: If zone ID cannot be retrieved
        """
        try:
            # Extract the parent domain if this is a wildcard domain
            query_domain = domain
            if domain.startswith('*.'):
                # For wildcard domains like *.tnode.ch, we need to query the parent domain (tnode.ch)
                query_domain = domain[2:]  # Remove the '*.' prefix
                logger.info(f"Wildcard domain detected. Using parent domain {query_domain} for zone lookup")
            
            response: Response = get(
                f"{self.api_base_url}/api/user/v1/zones?query={query_domain}&limit=1",
                headers={"accept": "application/json"},
                auth=BearerAuth(self.token),
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
            
            data = response.json()["data"]
            if not data:
                raise Exception(f"No zone found for domain {query_domain}")
                
            zone_id = data[0]["id"]
            logger.info(f"Zone ID for domain {domain} (queried as {query_domain}): {zone_id}")
            return zone_id
        except Exception as e:
            logger.error(f"Could not get zone ID for domain {domain}: {e}")
            raise Exception(f"Could not get zone ID for domain {domain}: {e}")
    
    def get_records(self, domain: str, zone_id: int) -> List[Dict[str, Any]]:
        """Get A records for a domain
        
        Args:
            domain: Domain name to get records for
            zone_id: Zone ID for the domain
            
        Returns:
            List of A, AAAA, and CNAME records
            
        Raises:
            Exception: If records cannot be retrieved
        """
        try:
            # For wildcard domains, we need to handle them specially
            is_wildcard = domain.startswith('*.')
            
            # Get all A records for the zone
            response: Response = get(
                f"{self.api_base_url}/api/user/v1/zones/{zone_id}/records",
                headers={"accept": "application/json"},
                auth=BearerAuth(self.token),
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
                
            all_records = response.json()["data"]
            logger.info(f"Found {len(all_records)} total records for zone ID {zone_id}")
            
            # If this is a wildcard domain, we need to find or create the wildcard record
            if is_wildcard:
                # For wildcard domains, we're looking for a record with name="*"
                filtered_records = []
                
                for record in all_records:
                    record_name = record.get("name", "")
                    if record_name == "*":
                        filtered_records.append(record)
                        logger.info(f"Found wildcard record: {record_name}")
                
                if not filtered_records:
                    logger.info(f"No wildcard record found for domain {domain}. You may need to create one.")
                    # Return an empty list - caller will need to handle this case
                    return []
                
                records = filtered_records
                logger.info(f"Filtered to {len(records)} wildcard A records for domain {domain}")
            else:
                # For normal domains, determine the relative record name.
                # Root domain (e.g., "example.com") uses an empty string.
                parts = domain.split('.')
                subdomain = ''
                if len(parts) > 2:
                    subdomain = parts[0]
                
                if subdomain:
                    # Filter for records with matching name
                    filtered_records = [r for r in all_records if r.get("name", "") == subdomain]
                    logger.info(f"Filtered to {len(filtered_records)} records for subdomain {subdomain}")
                    records = filtered_records
                else:
                    # This is the root domain, look for records with empty name or @ symbol
                    filtered_records = [r for r in all_records if r.get("name") in ["", "@", None]]
                    logger.info(f"Filtered to {len(filtered_records)} records for root domain")
                    records = filtered_records
                
            return records
        except Exception as e:
            logger.error(f"Could not get records for domain {domain}: {e}")
            raise Exception(f"Could not get records for domain {domain}: {e}")
    
    def update_record(self, zone_id: int, record: Dict[str, Any], new_ip: str) -> bool:
        """Update a DNS record with a new IP address
        
        Args:
            zone_id: Zone ID for the domain
            record: Record data to update
            new_ip: New IP address to set
            
        Returns:
            True if update was successful, False otherwise
            
        Raises:
            Exception: If record cannot be updated
        """
        try:
            record_id = record["id"]
            record_type = record["type"]
            record_name = record.get("name", "")
            record_ttl = record.get("ttl", 3600)
            
            # According to the API docs, the name field should contain just the prefix
            # For wildcard records, the name should be "*" (not "*.domain.com")
            logger.info(f"Updating record: ID={record_id}, Name={record_name}, Type={record_type}")
            
            send_data = {
                "type": record_type,
                "name": record_name,
                "ttl": record_ttl,
            }

            # Add the IP to the correct field based on record type
            if record_type == "A":
                send_data["ipv4"] = new_ip
            elif record_type == "AAAA":
                send_data["ipv6"] = new_ip
            else:
                logger.warning(f"Unsupported record type {record_type}, skipping update")
                return False
            
            response = put(
                f"{self.api_base_url}/api/user/v1/zones/{zone_id}/records/{record_id}",
                data=json.dumps(send_data),
                headers={"accept": "application/json", "content-type": "application/json"},
                auth=BearerAuth(self.token),
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
                
            data = response.json()["data"]
            
            # Verify the update was successful
            valid = (
                data["id"] == record_id
                and data["type"] == record_type
                and data["name"] == record_name
                and data.get("ttl") == record_ttl
            )
            if record_type == "A":
                valid = valid and data.get("ipv4") == new_ip
            elif record_type == "AAAA":
                valid = valid and data.get("ipv6") == new_ip
            if valid:
                logger.info(f"Successfully updated record {record_name} to {new_ip}")
                return True
            else:
                logger.error(f"Data received {data} does not match data sent {send_data}")
                return False
        except Exception as e:
            logger.error(f"Could not update record {record.get('name', 'unknown')}: {e}")
            raise Exception(f"Could not update record: {e}")
    
    def create_wildcard_record(self, zone_id: int, ip: str, ipv4: bool = True) -> bool:
        """Create a new wildcard A record in a zone
        
        Args:
            zone_id: Zone ID for the domain
            ip: IP address to set
            
        Returns:
            True if creation was successful, False otherwise
        """
        try:
            # According to the API docs, for wildcard records, the name should be "*"
            send_data = {
                "type": "A" if ipv4 else "AAAA",
                "name": "*",  # Just the asterisk for wildcard
                "ttl": 3600,
            }
            if ipv4:
                send_data["ipv4"] = ip
            else:
                send_data["ipv6"] = ip
            
            response = post(
                f"{self.api_base_url}/api/user/v1/zones/{zone_id}/records",
                data=json.dumps(send_data),
                headers={"accept": "application/json", "content-type": "application/json"},
                auth=BearerAuth(self.token),
            )
            
            if response.status_code not in [200, 201]:
                raise Exception(f"API returned status code {response.status_code}")
                
            data = response.json()["data"]
            logger.info(f"Successfully created wildcard record with ID {data['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Could not create wildcard record: {e}")
            return False

    def create_record(self, zone_id: int, name: str, ip: str, ipv4: bool = True) -> bool:
        """Create an A or AAAA record (generic helper)."""
        try:
            send_data = {
                "type": "A" if ipv4 else "AAAA",
                "name": name,
                "ttl": 3600,
            }
            if ipv4:
                send_data["ipv4"] = ip
            else:
                send_data["ipv6"] = ip

            response = post(
                f"{self.api_base_url}/api/user/v1/zones/{zone_id}/records",
                data=json.dumps(send_data),
                headers={"accept": "application/json", "content-type": "application/json"},
                auth=BearerAuth(self.token),
            )
            if response.status_code not in [200, 201]:
                raise Exception(f"API returned status code {response.status_code}")
            data = response.json()["data"]
            logger.info(f"Successfully created record with ID {data['id']}")
            return True
        except Exception as e:
            logger.error(f"Could not create record: {e}")
            return False

    @staticmethod
    def _record_exists(records: List[Dict[str, Any]], rec_type: str, acceptable_names: List[str]) -> bool:
        """Return True if a record of `rec_type` with name in acceptable_names exists."""
        return any(r.get("type") == rec_type and r.get("name") in acceptable_names for r in records)

    @staticmethod
    def _log_duplicates(records: List[Dict[str, Any]], rec_type: str, acceptable_names: List[str]) -> None:
        """Log a warning if more than one record exists for the same name and type."""
        dups = [r for r in records if r.get("type") == rec_type and r.get("name") in acceptable_names]
        if len(dups) > 1:
            logger.warning(f"Duplicate {rec_type} records found for names {acceptable_names}: {[d['id'] for d in dups]}")

    def _delete_record(self, zone_id: int, record_id: int) -> bool:
        """Delete a DNS record by ID."""
        try:
            response = delete(
                f"{self.api_base_url}/api/user/v1/zones/{zone_id}/records/{record_id}",
                headers={"accept": "application/json"},
                auth=BearerAuth(self.token),
            )
            if response.status_code != 204:
                raise Exception(f"Delete returned status {response.status_code}")
            logger.info(f"Deleted duplicate record ID {record_id}")
            return True
        except Exception as e:
            logger.error(f"Could not delete record {record_id}: {e}")
            return False

    def _deduplicate_records(self, zone_id: int, records: List[Dict[str, Any]], rec_type: str, acceptable_names: List[str]) -> None:
        """Ensure only one record of type/name exists. Keeps earliest (lowest id)."""
        dups = sorted([r for r in records if r.get("type") == rec_type and r.get("name") in acceptable_names], key=lambda r: r.get("id"))
        # keep first, delete rest
        for rec in dups[1:]:
            self._delete_record(zone_id, rec["id"])

    def update_dns(self) -> None:
        """Update DNS records for all domains if necessary"""
        try:
            # Get current IP address
            current_ipv4 = self.get_current_ip(ipv4=True)
            current_ipv6 = self.get_current_ip(ipv4=False)
            
            for domain in self.domains:
                try:
                    # Get zone ID for domain
                    zone_id = self.get_zone_id(domain)
                    
                    # Get records for domain
                    records = self.get_records(domain, zone_id)
                    
                    # Ensure required record types exist for this domain
                    is_wildcard = domain.startswith('*.')
                    # Determine acceptable names for root, wildcard or subdomain
                    if is_wildcard:
                        acceptable_names = ["*"]
                        record_name = "*"
                    else:
                        parts = domain.split('.')
                        if len(parts) > 2:
                            record_name = parts[0]
                            acceptable_names = [record_name]
                        else:
                            acceptable_names = ["", "@", None]
                            record_name = ""

                    # Log duplicates and create missing records
                    # Remove duplicates if present
                    self._deduplicate_records(zone_id, records, "A", acceptable_names)
                    self._deduplicate_records(zone_id, records, "AAAA", acceptable_names)
                    self._log_duplicates(records, "A", acceptable_names)
                    self._log_duplicates(records, "AAAA", acceptable_names)

                    # Refresh records list after potential deletes
                    records = self.get_records(domain, zone_id)

                    if not self._record_exists(records, "A", acceptable_names):
                        logger.info(f"Creating A record for {domain}")
                        self.create_record(zone_id, record_name, current_ipv4, ipv4=True)
                    if not self._record_exists(records, "AAAA", acceptable_names):
                        logger.info(f"Creating AAAA record for {domain}")
                        self.create_record(zone_id, record_name, current_ipv6, ipv4=False)

                    # Refresh records after any creation so that subsequent update logic has them
                    records = self.get_records(domain, zone_id)
                    
                    # If no records were found, log a warning and continue
                    if not records:
                        logger.warning(f"No matching records found for domain {domain}")
                        continue
                    
                    # Check if update is needed per record type
                    need_update_ipv4 = False
                    need_update_ipv6 = False
                    for record in records:
                        if record.get("type") == "A" and record.get("ipv4", "") != current_ipv4:
                            need_update_ipv4 = True
                        if record.get("type") == "AAAA" and record.get("ipv6", "") != current_ipv6:
                            need_update_ipv6 = True
                    
                    if not need_update_ipv4 and not need_update_ipv6:
                        logger.info(f"No update needed for domain {domain}.")
                        continue
                    
                    # Update records with the correct IP based on their type
                    update_count_ipv4 = 0
                    update_count_ipv6 = 0
                    for record in records:
                        if record.get("type") == "A":
                            if self.update_record(zone_id, record, current_ipv4):
                                update_count_ipv4 += 1
                        elif record.get("type") == "AAAA":
                            if self.update_record(zone_id, record, current_ipv6):
                                update_count_ipv6 += 1
                    
                    logger.info(f"Updated {update_count_ipv4} records for domain {domain} to {current_ipv4}")
                    logger.info(f"Updated {update_count_ipv6} records for domain {domain} to {current_ipv6}")
                    
                except Exception as e:
                    logger.error(f"Error processing domain {domain}: {e}")
            
        except Exception as e:
            logger.error(f"Error in update_dns: {e}")


def main():
    """Main entry point for the application"""
    # Load environment variables from .env file if it exists
    load_dotenv()
    
    parser = ArgumentParser(
        prog="ddns-hosttech",
        description=f"Update DNS entries on Hosttech nameservers (v{__version__})",
    )
    
    # Get default values from environment variables if available
    default_token = os.environ.get("TOKEN", "")
    default_domains = os.environ.get("DOMAINS", "").split(",") if os.environ.get("DOMAINS") else []
    default_interval = int(os.environ.get("INTERVAL", 5))
    
    # Set up command line arguments with defaults from environment variables
    parser.add_argument("-t", "--token", default=default_token, 
                        help="API token for authentication (can also be set via TOKEN env var)")
    parser.add_argument("-d", "--domain", action="append", help="Domain(s) to update (can also be set via DOMAINS env var)")
    parser.add_argument("-i", "--interval", type=int, default=default_interval, 
                        help=f"Update interval in minutes (default: {default_interval})")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}",
                        help="Show program's version number and exit")
    # add argument for non interval by --no-interval
    parser.add_argument("--no-interval", action="store_true", help="Do not run in interval mode")
    
    
    args = parser.parse_args()
    
    # If no domains provided via command line, use the ones from environment variables
    if not args.domain and default_domains:
        args.domain = default_domains
        
    # Validate required arguments
    if not args.token:
        parser.error("Token is required. Provide it with -t/--token or set TOKEN environment variable.")
        
    if not args.domain:
        parser.error("At least one domain is required. Provide it with -d/--domain or set DOMAINS environment variable.")
    
    # Remove empty domains (can happen if DOMAINS env var ends with a comma)
    args.domain = [d for d in args.domain if d]
    
    # Create API client
    api = HosttechApi(args.token, args.domain)
    
    # Convert interval to seconds
    interval_seconds = args.interval * 60
    
    logger.info(f"Starting DDNS updater for domains: {', '.join(args.domain)}")
    logger.info(f"Update interval: {args.interval} minutes")
    
    # Run initial update
    try:
        api.update_dns()
    except Exception as e:
        logger.error(f"Initial update failed: {e}")
    
    # Run periodic updates
    while True:
        if args.no_interval:
            break
        try:
            logger.info(f"Sleeping for {args.interval} minutes until next update")
            time.sleep(interval_seconds)
            logger.info("Running scheduled update")
            api.update_dns()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, exiting")
            break
        except Exception as e:
            logger.error(f"Error during scheduled update: {e}")
            # Continue with next iteration


if __name__ == "__main__":
    main()
    