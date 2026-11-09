# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub: **Security → Report a vulnerability** on this repository (private vulnerability reporting). Don't open a public issue for them.

Include what you found, how to reproduce it, and what it lets someone do. You'll get an acknowledgement, and a fix or an explanation, as soon as it can be looked at.

## Scope

- The server (`server/`): anything reachable over HTTP, for example a crash, reading files outside `dist/`, bypassing `MF_BASIC_AUTH`, spending a provider's quota, or leaking credentials or provider errors.
- The page: script injection or data leaking to other origins.
- Provider adapters: credential handling.

## Running it safely

The server is private by default (`HOST=127.0.0.1`). Before exposing it, read the Security section of the README: use `MF_BASIC_AUTH` or a sign-in proxy, and HTTPS in front.
