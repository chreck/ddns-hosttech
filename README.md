# Hosttech DDNS Updater

A Python application to automatically update DNS entries on Hosttech nameservers based on your current public IP address.

[![Docker Image Version](https://img.shields.io/docker/v/christopheck/hosttech-ddns?sort=semver&style=flat-square)](https://hub.docker.com/r/christopheck/hosttech-ddns)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- Automatically detects your current public IP address
- Updates DNS A (IPv4) and AAAA (IPv6) records on Hosttech nameservers
- Supports multiple domains and wildcard domains (`*.domain.com`)
- Configurable update interval (or single-run mode via `--no-interval`)
- Automatically cleans up duplicate DNS records
- Runs as a Docker container for easy deployment
- Environment variable support via `.env` file

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

#### Option 1: Pull from Docker Hub (recommended)

```bash
docker pull christopheck/hosttech-ddns:latest
```

#### Option 2: Build locally

```bash
docker build -t hosttech-ddns .
```

#### Option 3: Build multi-arch (amd64 & arm64) with Buildx

1. Create or select a Buildx builder (one-time setup):

```bash
# create (only first time)
docker buildx create --name multiarch --use
# or reuse if already created
docker buildx use multiarch
# start emulation for additional architectures
docker buildx inspect --bootstrap
```

2. Build and push a multi-architecture image:

```bash
VERSION=1.3.0  # adjust version

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t christopheck/hosttech-ddns:$VERSION \
  -t christopheck/hosttech-ddns:latest \
  --push .
```

`--push` uploads the manifest and both architecture layers directly to Docker Hub. If you also need a local image, remove `--push` and add `--load` (only loads the native architecture).

## Usage

### Command Line Arguments

- `-t, --token`: API token for authentication (required)
- `-d, --domain`: Domain(s) to update (required, can be specified multiple times)
- `-i, --interval`: Update interval in minutes (default: 5)
- `--no-interval`: Run once and exit (no loop)

### Local Usage

Run the script directly:

```bash
python ddns-hosttech.py -t YOUR_API_TOKEN -d example.com -d subdomain.example.com -i 10
```

### Docker Usage

#### Using Command Line Arguments

Run as a Docker container with the official image:

```bash
docker run -d --name hosttech-ddns christopheck/hosttech-ddns -t YOUR_API_TOKEN -d example.com -i 10
```

For multiple domains including wildcard domains:

```bash
docker run -d --name hosttech-ddns christopheck/hosttech-ddns -t YOUR_API_TOKEN -d example.com -d *.example.com -i 10
```

#### Using Environment Variables

Create an `.env` file with your configuration:

```
# Hosttech API token
TOKEN=your_token_here
# Domains to update, separated by commas
DOMAINS=example.com,*.example.com
# Update interval in minutes
INTERVAL=5
```

Then run the container with the `.env` file:

```bash
docker run -d --name hosttech-ddns --env-file .env christopheck/hosttech-ddns
```

## Docker Compose Example

A `docker-compose.yml` file is included in the repository. You can use it as follows:

```yaml
version: '3'

services:
  ddns-updater:
    image: christopheck/hosttech-ddns:latest
    container_name: hosttech-ddns
    restart: unless-stopped
    env_file:
      - .env
    # Alternatively, you can use environment variables directly
    # environment:
    #   - TOKEN=your_token_here
    #   - DOMAINS=example.com,*.example.com
    #   - INTERVAL=5
```

Then run:

```bash
docker-compose up -d
```

## Security Considerations

- Store your API token securely
- Use the `.env` file or Docker secrets for sensitive information
- The `.env` file is included in `.gitignore` and `.dockerignore` to prevent accidental exposure

## Versioning

This project follows [Semantic Versioning](https://semver.org/). The current version is specified in the `VERSION` file and can be checked with:

```bash
docker run --rm christopheck/hosttech-ddns --version
```

## License

This project is open source and available under the MIT License.

## Author

Christian Folini
