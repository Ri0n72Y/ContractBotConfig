# Reverse proxy for LAN OpenContracts

The MVP keeps OpenContracts inside a trusted network. The reverse proxy provides HTTPS and a stable internal hostname; it does not add application authentication.

## Option A: use OpenContracts bundled Traefik

OpenContracts' production configuration already contains Traefik with port 80→443 redirect, HTTPS routing, and ACME/Let's Encrypt.

The upstream checked-in configuration is written for a public DNS name and HTTP ACME challenge. Adapt its host rules and certificate resolver before using it on an internal deployment.

## Option B: Caddy

`Caddyfile.example` proxies one internal HTTPS hostname to the existing OpenContracts HTTP endpoint.

Two certificate patterns are common:

```text
publicly valid certificate
  use a DNS name/certificate flow your environment can validate

internal CA
  use Caddy `tls internal`
  install/trust Caddy's root CA on every Harness host
```

Do not solve certificate errors by disabling TLS verification in WorkBuddy/Harness.

## Option C: Nginx

`nginx-opencontracts.conf.example` assumes the organization already has a certificate/key from an internal or public CA. Replace the placeholders and upstream address.

## Network rule

Regardless of proxy choice, firewall/NAT configuration must keep the service unreachable from untrusted networks. Remote Harnesses should connect through the approved LAN/VPN/network overlay first.
