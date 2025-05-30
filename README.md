# Hosttech DDNS Updater

A Python application to automatically update DNS entries on Hosttech nameservers based on your current public IP address.

## Features

- Automatically detects your current public IP address
- Updates DNS A records on Hosttech nameservers
- Supports multiple domains
- Configurable update interval
- Runs as a Docker container for easy deployment

## Requirements

- Python 3.6+
- Docker (optional, for containerized deployment)
- Hosttech API token from https://www.myhosttech.eu/user/dns/api

## Installation

### Local Installation

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

### Docker Installation

1. Build the Docker image:
   ```
   docker build -t hosttech-ddns .
   ```

## Usage

### Command Line Arguments

- `-t, --token`: API token for authentication (required)
- `-d, --domain`: Domain(s) to update (required, can be specified multiple times)
- `-i, --interval`: Update interval in minutes (default: 5)

### Local Usage

Run the script directly:

```bash
python ddns-hosttech.py -t YOUR_API_TOKEN -d example.com -d subdomain.example.com -i 10
```

### Docker Usage

Run as a Docker container:

```bash
docker run -d --name hosttech-ddns hosttech-ddns -t YOUR_API_TOKEN -d example.com -i 10
```

For multiple domains:

```bash
docker run -d --name hosttech-ddns hosttech-ddns -t YOUR_API_TOKEN -d example.com -d subdomain.example.com -i 10
```

## Docker Compose Example

Create a `docker-compose.yml` file:

```yaml
version: '3'

services:
  ddns-updater:
    build: .
    container_name: hosttech-ddns
    restart: unless-stopped
    command: -t YOUR_API_TOKEN -d example.com -i 10
```

Then run:

```bash
docker-compose up -d
```

## Security Considerations

- Store your API token securely
- Consider using Docker secrets or environment variables for the token in production

## License

This project is open source and available under the MIT License.
