# PATY Outbound

**Telephony routing and dispatch for Pipecat.**

`pipecat-outbound` is a module designed to handle outbound telephony calls using various providers (Daily, Telnyx, etc.) with a unified interface. It integrates seamlessly with Pipecat to provide real-time audio processing capabilities.

## Features

- **Unified Interface**: outbound calling abstraction for multiple providers.
- **Configurable Routing**: Route calls based on destination patterns (regex).
- **Flexible Providers**: Support for Daily.co, Telnyx, and extensible for others.
- **Pipecat Integration**: Returns ready-to-use Pipecat transports.

## Quick Start

```python
from pipecat_outbound.caller import OutboundCaller

# Initialize with config
caller = OutboundCaller("telephony.yaml")

# Initiate a call
session, transport = await caller.call(to="+15550101")

# Use the transport with Pipecat pipeline
# ...
```

## Installation

```bash
pip install pipecat-outbound
```
