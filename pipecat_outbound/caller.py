# outbound/caller.py
"""
Outbound Caller Module

This module provides the main entry point for initiating outbound calls through various
telephony providers. It handles configuration loading, provider management, and call routing
based on configurable rules.
"""
import yaml
import re
import os

from .protocol import OutboundProvider, CallSession, CallRequest
from pipecat.transports.base_transport import BaseTransport
from .providers.websocket_base import WebSocketConnectionCoordinator
from .providers.daily import DailyOutboundProvider

# Missing providers commented out until implemented
# from .providers.telnyx import TelnyxOutboundProvider
# from .providers.twilio import TwilioOutboundProvider
# from .providers.plivo import PlivoOutboundProvider
# from .providers.exotel import ExotelOutboundProvider

class OutboundCaller:
    """
    Manages outbound calling capabilities across multiple providers.
    
    This class is responsible for loading configuration, initializing available providers,
    and routing outbound calls to the appropriate provider based on destination numbers.
    """
    
    def __init__(self, config_path: str):
        """
        Initialize the OutboundCaller with a configuration file.
        
        Args:
            config_path: Path to the YAML configuration file containing provider and routing settings.
        """
        self.config = self._load_config(config_path)
        self.coordinator = WebSocketConnectionCoordinator()
        self.providers = self._init_providers()
    
    def _load_config(self, path: str) -> dict:
        """
        Load and parse the YAML configuration file.
        
        Args:
            path: Path to the YAML file.
            
        Returns:
            dict: The parsed configuration with environment variables expanded.
        """
        with open(path) as f:
            config = yaml.safe_load(f)
        
        # Expand env vars
        return self._expand_env_vars(config)
    
    def _expand_env_vars(self, obj):
        """
        Recursively expand environment variables in the configuration object.
        
        This method replaces strings in the format `${VAR_NAME}` with the value of the
        environment variable `VAR_NAME`. Defaults to the original string if not found.
        
        Args:
            obj: The configuration object (dict, list, or str) to process.
            
        Returns:
            The processed object with environment variables expanded.
        """
        if isinstance(obj, str):
            # Replace ${VAR} with os.environ["VAR"]
            return re.sub(
                r'\$\{(\w+)\}',
                lambda m: os.environ.get(m.group(1), m.group(0)),
                obj
            )
        elif isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(v) for v in obj]
        return obj
    
    def _init_providers(self) -> dict[str, OutboundProvider]:
        """
        Initialize all configured providers.
        
        Instantiates provider classes based on the 'providers' section of the configuration.
        
        Returns:
            dict[str, OutboundProvider]: A dictionary mapping provider names to initialized provider instances.
        """
        providers = {}
        factory = {
            "daily": DailyOutboundProvider,
            # "telnyx": lambda c: TelnyxOutboundProvider(c, self.coordinator),
            # "twilio": lambda c: TwilioOutboundProvider(c, self.coordinator),
            # "plivo": lambda c: PlivoOutboundProvider(c, self.coordinator),
            # "exotel": lambda c: ExotelOutboundProvider(c, self.coordinator),
        }
        
        for name, cfg in self.config["providers"].items():
            provider_type = cfg["type"]
            if provider_type in factory:
                providers[name] = factory[provider_type](cfg)
        
        return providers
    
    def _select_provider(self, to: str) -> OutboundProvider:
        """
        Route to appropriate provider based on config rules.
        
        Evaluates the 'routing' section of the configuration to determine which provider
        should handle a call to the given destination number.
        
        Args:
            to: The destination phone number or SIP URI.
            
        Returns:
            OutboundProvider: The selected provider instance.
        """
        for rule in self.config.get("routing", {}).get("rules", []):
            pattern = rule["pattern"].replace("*", ".*")
            if re.match(pattern, to):
                return self.providers[rule["provider"]]
        
        default = self.config.get("routing", {}).get("default", "daily")
        return self.providers[default]
    
    async def call(self, to: str, from_: str = None) -> tuple[CallSession, BaseTransport]:
        """
        Initiate an outbound call - provider selected automatically.
        
        This is the main public method to start a call. It selects the appropriate provider,
        initiates the call session, and retrieves the transport for the call.
        
        Args:
            to: The destination identifier (e.g., phone number).
            from_: Optional source identifier (e.g., caller ID).
            
        Returns:
            tuple[CallSession, BaseTransport]: A tuple containing the active call session
            and the transport to be used for the call.
        """
        provider = self._select_provider(to)
        
        session = await provider.initiate_call(CallRequest(to=to, from_=from_))
        transport = await provider.get_transport(session)
        
        return session, transport