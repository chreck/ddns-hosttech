#!/usr/bin/env python3
# Documentation at https://www.hosttech.ch/blog/neue-api/
# and https://api.ns1.hosttech.eu/api/documentation/#/

import json
import time
import logging
from typing import List, Dict, Any, Optional
from requests import Response, get, put, auth
from argparse import ArgumentParser

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
            response: Response = get(
                f"{self.api_base_url}/api/user/v1/zones?query={domain}&limit=1",
                headers={"accept": "application/json"},
                auth=BearerAuth(self.token),
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
                
            zone_id = response.json()["data"][0]["id"]
            logger.info(f"Zone ID for domain {domain}: {zone_id}")
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
            response: Response = get(
                f"{self.api_base_url}/api/user/v1/zones/{zone_id}/records?type=A",
                headers={"accept": "application/json"},
                auth=BearerAuth(self.token),
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status code {response.status_code}")
                
            records = response.json()["data"]
            logger.info(f"Found {len(records)} A records for domain {domain}")
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
            record_ttl = 3600
            
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
    parser = ArgumentParser(
        prog="ddns-hosttech",
        description="Update DNS entries on Hosttech nameservers",
    )
    
    parser.add_argument("-t", "--token", required=True, help="API token for authentication")
    parser.add_argument("-d", "--domain", required=True, action="append", help="Domain(s) to update")
    parser.add_argument("-i", "--interval", type=int, default=5, help="Update interval in minutes (default: 5)")
    
    args = parser.parse_args()
    
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
    