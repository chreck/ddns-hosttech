#!/usr/bin/env python3
# Documentation at https://www.hosttech.ch/blog/neue-api/
# and https://api.ns1.hosttech.eu/api/documentation/#/

import json
import time
import logging
import os
from typing import List, Dict, Any, Optional
from requests import Response, get, put, auth
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
        
    def get_current_ip(self) -> str:
        """Get the current public IP address
        
        Returns:
            Current public IP address as string
            
        Raises:
            Exception: If IP address cannot be retrieved
        """
        try:
            response: Response = get("https://ipv4.ip.nf/me.json")
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
                
            ip = response.json()["ip"]["ip"]
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
            List of A records
            
        Raises:
            Exception: If records cannot be retrieved
        """
        try:
            # For wildcard domains, we need to handle them specially
            is_wildcard = domain.startswith('*.')
            
            # Get all A records for the zone
            response: Response = get(
                f"{self.api_base_url}/api/user/v1/zones/{zone_id}/records?type=A",
                headers={"accept": "application/json"},
                auth=BearerAuth(self.token),
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
                
            all_records = response.json()["data"]
            logger.info(f"Found {len(all_records)} total A records for zone ID {zone_id}")
            
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
                # For normal domains, filter to get the specific subdomain
                # The API expects the name field to contain just the subdomain part
                subdomain = domain.split('.', 1)[0] if '.' in domain else ""
                
                if subdomain:
                    # Filter for records with matching name
                    filtered_records = [r for r in all_records if r.get("name", "") == subdomain]
                    logger.info(f"Filtered to {len(filtered_records)} A records for subdomain {subdomain}")
                    records = filtered_records
                else:
                    # This is the root domain, look for records with empty name or @ symbol
                    filtered_records = [r for r in all_records if r.get("name", "") in ["", "@"]]
                    logger.info(f"Filtered to {len(filtered_records)} A records for root domain")
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
                "ipv4": new_ip,
                "ttl": record_ttl,
            }
            
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
            if (
                data["id"] == record_id
                and data["type"] == record_type
                and data["name"] == record_name
                and data["ipv4"] == new_ip
                and data["ttl"] == record_ttl
            ):
                logger.info(f"Successfully updated record {record_name} to {new_ip}")
                return True
            else:
                logger.error(f"Data received {data} does not match data sent {send_data}")
                return False
        except Exception as e:
            logger.error(f"Could not update record {record.get('name', 'unknown')}: {e}")
            raise Exception(f"Could not update record: {e}")
    
    def create_wildcard_record(self, zone_id: int, ip: str) -> bool:
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
                "type": "A",
                "name": "*",  # Just the asterisk for wildcard
                "ipv4": ip,
                "ttl": 3600,
            }
            
            response = put(
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
    
    def update_dns(self) -> None:
        """Update DNS records for all domains if necessary"""
        try:
            # Get current IP address
            current_ip = self.get_current_ip()
            
            for domain in self.domains:
                try:
                    # Get zone ID for domain
                    zone_id = self.get_zone_id(domain)
                    
                    # Get records for domain
                    records = self.get_records(domain, zone_id)
                    
                    # For wildcard domains, we might need to create the record if it doesn't exist
                    if domain.startswith('*.') and not records:
                        logger.info(f"Creating new wildcard record for {domain}")
                        if self.create_wildcard_record(zone_id, current_ip):
                            logger.info(f"Successfully created wildcard record for {domain}")
                        continue
                    
                    # If no records were found, log a warning and continue
                    if not records:
                        logger.warning(f"No matching records found for domain {domain}")
                        continue
                    
                    # Check if update is needed
                    need_update = False
                    for record in records:
                        if record.get("ipv4", "") != current_ip:
                            need_update = True
                            break
                    
                    if not need_update:
                        logger.info(f"No update needed for domain {domain}, IP already set to {current_ip}")
                        continue
                    
                    # Update records
                    update_count = 0
                    for record in records:
                        if self.update_record(zone_id, record, current_ip):
                            update_count += 1
                    
                    logger.info(f"Updated {update_count} records for domain {domain} to {current_ip}")
                    
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
        description="Update DNS entries on Hosttech nameservers",
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
    