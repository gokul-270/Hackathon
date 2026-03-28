#!/usr/bin/env python3
"""
Configuration Management and Validation System
Provides robust configuration handling with schema validation
"""
import logging
import os
import yaml
import json
from typing import Dict, List, Any, Tuple, Optional, Union
from dataclasses import dataclass, field
from enum import Enum


class ConfigValidationError(Exception):
    """Configuration validation error"""
    pass


class ConfigType(Enum):
    """Configuration value types"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"


@dataclass
class ConfigConstraint:
    """Configuration value constraint"""
    type: ConfigType
    required: bool = True
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    allowed_values: Optional[List[Any]] = None
    regex_pattern: Optional[str] = None
    schema: Optional[Dict[str, 'ConfigConstraint']] = None  # For nested dicts
    item_type: Optional[ConfigType] = None  # For list items
    default_value: Any = None


@dataclass
class ValidationResult:
    """Configuration validation result"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    fixed_values: Dict[str, Any] = field(default_factory=dict)


class ConfigurationManager:
    """
    Configuration management system with validation and schema enforcement
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Define the complete vehicle control configuration schema
        self.schema = self._build_configuration_schema()
        
        # Loaded configuration
        self._config: Dict[str, Any] = {}
        self._config_source: Optional[str] = None
        
        # Validation history
        self._validation_history: List[ValidationResult] = []
        
        self.logger.info("Configuration manager initialized")
    
    def _build_configuration_schema(self) -> Dict[str, ConfigConstraint]:
        """Build the complete configuration schema"""
        return {
            # Basic ROS2 parameters
            'joint_names': ConfigConstraint(
                type=ConfigType.LIST,
                required=True,
                min_length=1,
                max_length=10,
                item_type=ConfigType.STRING,
                default_value=['joint2', 'joint3', 'joint4', 'joint5']
            ),
            
            # Control frequencies
            'control_frequency': ConfigConstraint(
                type=ConfigType.FLOAT,
                required=True,
                min_value=1.0,
                max_value=1000.0,
                default_value=100.0
            ),
            
            'joint_state_frequency': ConfigConstraint(
                type=ConfigType.FLOAT,
                required=True,
                min_value=1.0,
                max_value=500.0,
                default_value=50.0
            ),
            
            'gpio_frequency': ConfigConstraint(
                type=ConfigType.FLOAT,
                required=True,
                min_value=1.0,
                max_value=100.0,
                default_value=10.0
            ),
            
            'status_frequency': ConfigConstraint(
                type=ConfigType.FLOAT,
                required=True,
                min_value=0.1,
                max_value=50.0,
                default_value=5.0
            ),
            
            # Timeout settings
            'cmd_vel_timeout': ConfigConstraint(
                type=ConfigType.FLOAT,
                required=True,
                min_value=0.1,
                max_value=10.0,
                default_value=1.0
            ),
            
            'service_call_timeout': ConfigConstraint(
                type=ConfigType.FLOAT,
                required=False,
                min_value=1.0,
                max_value=30.0,
                default_value=10.0
            ),
            
            'hardware_detection_timeout': ConfigConstraint(
                type=ConfigType.FLOAT,
                required=False,
                min_value=0.5,
                max_value=10.0,
                default_value=2.0
            ),
            
            # Physical parameters
            'physical_params': ConfigConstraint(
                type=ConfigType.DICT,
                required=True,
                schema={
                    'wheel_diameter': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=True,
                        min_value=0.05,
                        max_value=0.5,
                        default_value=0.15
                    ),
                    'driving_gear_ratio': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=True,
                        min_value=1.0,
                        max_value=50.0,
                        default_value=5.0
                    ),
                    'steering_gear_ratio': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=True,
                        min_value=1.0,
                        max_value=100.0,
                        default_value=10.0
                    ),
                    'wheelbase': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=0.1,
                        max_value=3.0,
                        default_value=1.0
                    ),
                    'track_width': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=0.1,
                        max_value=3.0,
                        default_value=0.8
                    ),
                    'steering_limits': ConfigConstraint(
                        type=ConfigType.DICT,
                        required=True,
                        schema={
                            'min': ConfigConstraint(
                                type=ConfigType.FLOAT,
                                required=True,
                                min_value=-90.0,
                                max_value=0.0,
                                default_value=-45.0
                            ),
                            'max': ConfigConstraint(
                                type=ConfigType.FLOAT,
                                required=True,
                                min_value=0.0,
                                max_value=90.0,
                                default_value=45.0
                            )
                        }
                    )
                }
            ),
            
            # Safety parameters
            'safety_params': ConfigConstraint(
                type=ConfigType.DICT,
                required=False,
                schema={
                    'max_velocity': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=0.1,
                        max_value=5.0,
                        default_value=2.0
                    ),
                    'max_acceleration': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=0.1,
                        max_value=10.0,
                        default_value=2.0
                    ),
                    'emergency_stop_deceleration': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=1.0,
                        max_value=20.0,
                        default_value=5.0
                    ),
                    'motor_temperature_limit': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=50.0,
                        max_value=100.0,
                        default_value=75.0
                    ),
                    'voltage_limits': ConfigConstraint(
                        type=ConfigType.DICT,
                        required=False,
                        schema={
                            'min': ConfigConstraint(
                                type=ConfigType.FLOAT,
                                required=False,
                                min_value=15.0,
                                max_value=25.0,
                                default_value=20.0
                            ),
                            'max': ConfigConstraint(
                                type=ConfigType.FLOAT,
                                required=False,
                                min_value=25.0,
                                max_value=35.0,
                                default_value=30.0
                            )
                        }
                    )
                }
            ),
            
            # Motor parameters
            'motor_params': ConfigConstraint(
                type=ConfigType.DICT,
                required=False,
                schema={
                    'drive_motors': ConfigConstraint(
                        type=ConfigType.LIST,
                        required=False,
                        item_type=ConfigType.INTEGER,
                        min_length=1,
                        max_length=10,
                        default_value=[0, 1]
                    ),
                    'steering_motors': ConfigConstraint(
                        type=ConfigType.LIST,
                        required=False,
                        item_type=ConfigType.INTEGER,
                        min_length=1,
                        max_length=10,
                        default_value=[2, 3, 4]
                    ),
                    'can_bus_id': ConfigConstraint(
                        type=ConfigType.INTEGER,
                        required=False,
                        min_value=0,
                        max_value=15,
                        default_value=0
                    ),
                    'current_limit': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=1.0,
                        max_value=100.0,
                        default_value=20.0
                    ),
                    'velocity_limit': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=1.0,
                        max_value=200.0,
                        default_value=50.0
                    )
                }
            ),
            
            # GPIO configuration
            'gpio_params': ConfigConstraint(
                type=ConfigType.DICT,
                required=False,
                schema={
                    'emergency_stop_pin': ConfigConstraint(
                        type=ConfigType.INTEGER,
                        required=False,
                        min_value=0,
                        max_value=40,
                        default_value=16
                    ),
                    'brake_pin': ConfigConstraint(
                        type=ConfigType.INTEGER,
                        required=False,
                        min_value=0,
                        max_value=40,
                        default_value=18
                    ),
                    'direction_pins': ConfigConstraint(
                        type=ConfigType.LIST,
                        required=False,
                        item_type=ConfigType.INTEGER,
                        min_length=2,
                        max_length=2,
                        default_value=[20, 21]
                    ),
                    'led_pins': ConfigConstraint(
                        type=ConfigType.DICT,
                        required=False,
                        schema={
                            'green': ConfigConstraint(type=ConfigType.INTEGER, default_value=26),
                            'yellow': ConfigConstraint(type=ConfigType.INTEGER, default_value=19),
                            'red': ConfigConstraint(type=ConfigType.INTEGER, default_value=13),
                            'error': ConfigConstraint(type=ConfigType.INTEGER, default_value=6)
                        }
                    )
                }
            ),
            
            # Diagnostic settings
            'diagnostic_params': ConfigConstraint(
                type=ConfigType.DICT,
                required=False,
                schema={
                    'enable_diagnostics': ConfigConstraint(
                        type=ConfigType.BOOLEAN,
                        required=False,
                        default_value=True
                    ),
                    'diagnostic_interval': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=1.0,
                        max_value=60.0,
                        default_value=5.0
                    ),
                    'diagnostic_level': ConfigConstraint(
                        type=ConfigType.STRING,
                        required=False,
                        allowed_values=['BASIC', 'DETAILED', 'COMPREHENSIVE'],
                        default_value='DETAILED'
                    ),
                    'export_reports': ConfigConstraint(
                        type=ConfigType.BOOLEAN,
                        required=False,
                        default_value=False
                    ),
                    'report_export_path': ConfigConstraint(
                        type=ConfigType.STRING,
                        required=False,
                        default_value='/tmp/vehicle_diagnostics'
                    )
                }
            ),
            
            # Logging configuration
            'logging_params': ConfigConstraint(
                type=ConfigType.DICT,
                required=False,
                schema={
                    'log_level': ConfigConstraint(
                        type=ConfigType.STRING,
                        required=False,
                        allowed_values=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default_value='INFO'
                    ),
                    'log_to_file': ConfigConstraint(
                        type=ConfigType.BOOLEAN,
                        required=False,
                        default_value=False
                    ),
                    'log_file_path': ConfigConstraint(
                        type=ConfigType.STRING,
                        required=False,
                        default_value='/tmp/vehicle_control.log'
                    ),
                    'log_rotation': ConfigConstraint(
                        type=ConfigType.BOOLEAN,
                        required=False,
                        default_value=True
                    ),
                    'max_log_size_mb': ConfigConstraint(
                        type=ConfigType.FLOAT,
                        required=False,
                        min_value=1.0,
                        max_value=100.0,
                        default_value=10.0
                    )
                }
            )
        }
    
    def load_configuration(self, config_path: str) -> ValidationResult:
        """
        Load configuration from file with validation
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            ValidationResult with loading and validation status
        """
        try:
            self.logger.info(f"Loading configuration from {config_path}")
            
            # Check if file exists
            if not os.path.exists(config_path):
                return ValidationResult(
                    is_valid=False,
                    errors=[f"Configuration file not found: {config_path}"]
                )
            
            # Load configuration based on file extension
            config_data = {}
            
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                with open(config_path, 'r') as f:
                    config_data = yaml.safe_load(f) or {}
                    
            elif config_path.endswith('.json'):
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                    
            else:
                return ValidationResult(
                    is_valid=False,
                    errors=[f"Unsupported configuration file format: {config_path}"]
                )
            
            # Extract vehicle_control parameters if nested
            if 'vehicle_control' in config_data:
                if 'ros__parameters' in config_data['vehicle_control']:
                    config_data = config_data['vehicle_control']['ros__parameters']
                else:
                    config_data = config_data['vehicle_control']
            
            # Validate configuration
            validation_result = self.validate_configuration(config_data)
            
            if validation_result.is_valid:
                self._config = config_data
                self._config_source = config_path
                self.logger.info(f"Configuration loaded successfully from {config_path}")
            else:
                self.logger.error(f"Configuration validation failed for {config_path}")
                for error in validation_result.errors:
                    self.logger.error(f"  - {error}")
            
            # Store validation result
            self._validation_history.append(validation_result)
            
            return validation_result
            
        except Exception as e:
            error_msg = f"Failed to load configuration from {config_path}: {e}"
            self.logger.error(error_msg)
            
            result = ValidationResult(
                is_valid=False,
                errors=[error_msg]
            )
            self._validation_history.append(result)
            return result
    
    def validate_configuration(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate configuration against schema
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            ValidationResult with validation status and any fixes applied
        """
        result = ValidationResult(is_valid=True)
        
        try:
            self.logger.debug("Starting configuration validation...")
            
            # Validate all schema parameters
            validated_config = {}
            
            for param_name, constraint in self.schema.items():
                validation = self._validate_parameter(
                    param_name, 
                    config.get(param_name), 
                    constraint,
                    f"config.{param_name}"
                )
                
                # Collect errors and warnings
                result.errors.extend(validation.errors)
                result.warnings.extend(validation.warnings)
                
                # Apply fixed values
                if param_name in validation.fixed_values:
                    validated_config[param_name] = validation.fixed_values[param_name]
                    result.fixed_values[param_name] = validation.fixed_values[param_name]
                elif param_name in config:
                    validated_config[param_name] = config[param_name]
                elif constraint.required:
                    if constraint.default_value is not None:
                        validated_config[param_name] = constraint.default_value
                        result.fixed_values[param_name] = constraint.default_value
                        result.warnings.append(
                            f"Missing required parameter '{param_name}', using default: {constraint.default_value}"
                        )
                    else:
                        result.errors.append(f"Missing required parameter: {param_name}")
            
            # Check for unknown parameters
            for param_name in config:
                if param_name not in self.schema:
                    result.warnings.append(f"Unknown parameter: {param_name}")
            
            # Update validation status
            result.is_valid = len(result.errors) == 0
            
            # Apply fixes if validation passed
            if result.is_valid and result.fixed_values:
                for key, value in result.fixed_values.items():
                    self._set_nested_value(config, key, value)
            
            self.logger.debug(f"Configuration validation completed: {result.is_valid}")
            if result.errors:
                for error in result.errors:
                    self.logger.error(f"Validation error: {error}")
            if result.warnings:
                for warning in result.warnings:
                    self.logger.warning(f"Validation warning: {warning}")
            
        except Exception as e:
            result.is_valid = False
            result.errors.append(f"Configuration validation failed: {e}")
            self.logger.error(f"Configuration validation exception: {e}")
        
        return result
    
    def _validate_parameter(self, 
                          param_name: str, 
                          value: Any, 
                          constraint: ConfigConstraint,
                          param_path: str) -> ValidationResult:
        """Validate a single parameter against its constraint"""
        result = ValidationResult(is_valid=True)
        
        # Handle missing values
        if value is None:
            if constraint.required:
                if constraint.default_value is not None:
                    result.fixed_values[param_name] = constraint.default_value
                    result.warnings.append(f"{param_path}: Missing value, using default: {constraint.default_value}")
                else:
                    result.errors.append(f"{param_path}: Required parameter is missing")
                    result.is_valid = False
            return result
        
        # Type validation
        if not self._validate_type(value, constraint.type):
            result.errors.append(f"{param_path}: Expected {constraint.type.value}, got {type(value).__name__}")
            result.is_valid = False
            return result
        
        # Range validation for numbers
        if constraint.type in [ConfigType.INTEGER, ConfigType.FLOAT]:
            if constraint.min_value is not None and value < constraint.min_value:
                result.errors.append(f"{param_path}: Value {value} below minimum {constraint.min_value}")
                result.is_valid = False
            
            if constraint.max_value is not None and value > constraint.max_value:
                result.errors.append(f"{param_path}: Value {value} above maximum {constraint.max_value}")
                result.is_valid = False
        
        # Length validation for strings and lists
        if constraint.type in [ConfigType.STRING, ConfigType.LIST]:
            length = len(value)
            if constraint.min_length is not None and length < constraint.min_length:
                result.errors.append(f"{param_path}: Length {length} below minimum {constraint.min_length}")
                result.is_valid = False
            
            if constraint.max_length is not None and length > constraint.max_length:
                result.errors.append(f"{param_path}: Length {length} above maximum {constraint.max_length}")
                result.is_valid = False
        
        # Allowed values validation
        if constraint.allowed_values is not None:
            if value not in constraint.allowed_values:
                result.errors.append(f"{param_path}: Value '{value}' not in allowed values: {constraint.allowed_values}")
                result.is_valid = False
        
        # Regex pattern validation for strings
        if constraint.type == ConfigType.STRING and constraint.regex_pattern:
            import re
            if not re.match(constraint.regex_pattern, value):
                result.errors.append(f"{param_path}: Value '{value}' does not match pattern: {constraint.regex_pattern}")
                result.is_valid = False
        
        # List item validation
        if constraint.type == ConfigType.LIST and constraint.item_type:
            for i, item in enumerate(value):
                if not self._validate_type(item, constraint.item_type):
                    result.errors.append(f"{param_path}[{i}]: Expected {constraint.item_type.value}, got {type(item).__name__}")
                    result.is_valid = False
        
        # Nested dictionary validation
        if constraint.type == ConfigType.DICT and constraint.schema:
            if not isinstance(value, dict):
                result.errors.append(f"{param_path}: Expected dictionary")
                result.is_valid = False
            else:
                for nested_key, nested_constraint in constraint.schema.items():
                    nested_result = self._validate_parameter(
                        nested_key,
                        value.get(nested_key),
                        nested_constraint,
                        f"{param_path}.{nested_key}"
                    )
                    
                    result.errors.extend(nested_result.errors)
                    result.warnings.extend(nested_result.warnings)
                    
                    # Apply nested fixes
                    for fix_key, fix_value in nested_result.fixed_values.items():
                        if nested_key not in value:
                            value[nested_key] = fix_value
                        result.fixed_values[f"{param_name}.{fix_key}"] = fix_value
                    
                    if not nested_result.is_valid:
                        result.is_valid = False
        
        return result
    
    def _validate_type(self, value: Any, expected_type: ConfigType) -> bool:
        """Validate value type"""
        if expected_type == ConfigType.STRING:
            return isinstance(value, str)
        elif expected_type == ConfigType.INTEGER:
            return isinstance(value, int)
        elif expected_type == ConfigType.FLOAT:
            return isinstance(value, (int, float))
        elif expected_type == ConfigType.BOOLEAN:
            return isinstance(value, bool)
        elif expected_type == ConfigType.LIST:
            return isinstance(value, list)
        elif expected_type == ConfigType.DICT:
            return isinstance(value, dict)
        else:
            return False
    
    def _set_nested_value(self, config: Dict[str, Any], key_path: str, value: Any):
        """Set a nested configuration value"""
        keys = key_path.replace('config.', '').split('.')
        current = config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def get_configuration(self) -> Dict[str, Any]:
        """Get the current validated configuration"""
        return self._config.copy()
    
    def get_parameter(self, param_path: str, default: Any = None) -> Any:
        """
        Get a specific parameter value using dot notation
        
        Args:
            param_path: Parameter path (e.g., 'physical_params.wheel_diameter')
            default: Default value if parameter not found
            
        Returns:
            Parameter value or default
        """
        keys = param_path.split('.')
        current = self._config
        
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default
    
    def set_parameter(self, param_path: str, value: Any) -> bool:
        """
        Set a parameter value with validation
        
        Args:
            param_path: Parameter path (e.g., 'physical_params.wheel_diameter')
            value: New parameter value
            
        Returns:
            True if parameter was set successfully
        """
        try:
            # Find the appropriate constraint
            constraint = None
            schema_keys = param_path.split('.')
            current_schema = self.schema
            
            for key in schema_keys:
                if key in current_schema:
                    constraint = current_schema[key]
                    if constraint.schema:
                        current_schema = constraint.schema
                    break
            
            if constraint:
                # Validate the new value
                validation = self._validate_parameter('temp', value, constraint, param_path)
                if not validation.is_valid:
                    self.logger.error(f"Cannot set {param_path}: {validation.errors}")
                    return False
                
                # Apply any fixes
                if 'temp' in validation.fixed_values:
                    value = validation.fixed_values['temp']
            
            # Set the value
            self._set_nested_value(self._config, f"config.{param_path}", value)
            self.logger.info(f"Parameter {param_path} set to {value}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set parameter {param_path}: {e}")
            return False
    
    def export_configuration(self, output_path: str, format: str = 'yaml') -> bool:
        """
        Export current configuration to file
        
        Args:
            output_path: Output file path
            format: Export format ('yaml' or 'json')
            
        Returns:
            True if export successful
        """
        try:
            if format.lower() == 'yaml':
                with open(output_path, 'w') as f:
                    yaml.dump(self._config, f, default_flow_style=False, indent=2)
            elif format.lower() == 'json':
                with open(output_path, 'w') as f:
                    json.dump(self._config, f, indent=2)
            else:
                self.logger.error(f"Unsupported export format: {format}")
                return False
            
            self.logger.info(f"Configuration exported to {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export configuration: {e}")
            return False
    
    def get_default_configuration(self) -> Dict[str, Any]:
        """Generate default configuration from schema"""
        default_config = {}
        
        def build_defaults(schema: Dict[str, ConfigConstraint], target: Dict[str, Any]):
            for param_name, constraint in schema.items():
                if constraint.type == ConfigType.DICT and constraint.schema:
                    # Always create dict structure for nested parameters
                    target[param_name] = {}
                    build_defaults(constraint.schema, target[param_name])
                elif constraint.default_value is not None:
                    target[param_name] = constraint.default_value
        
        build_defaults(self.schema, default_config)
        return default_config
    
    def create_default_config_file(self, output_path: str) -> bool:
        """Create a default configuration file"""
        try:
            default_config = self.get_default_configuration()
            
            with open(output_path, 'w') as f:
                yaml.dump({
                    'vehicle_control': {
                        'ros__parameters': default_config
                    }
                }, f, default_flow_style=False, indent=2)
            
            self.logger.info(f"Default configuration file created at {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create default config file: {e}")
            return False
    
    def get_validation_history(self) -> List[ValidationResult]:
        """Get configuration validation history"""
        return self._validation_history.copy()
    
    def get_schema_documentation(self) -> str:
        """Generate human-readable schema documentation"""
        def document_constraint(name: str, constraint: ConfigConstraint, indent: int = 0) -> str:
            spaces = "  " * indent
            doc = f"{spaces}{name} ({constraint.type.value})"
            
            if constraint.required:
                doc += " [REQUIRED]"
            else:
                doc += " [OPTIONAL]"
            
            if constraint.default_value is not None:
                doc += f" = {constraint.default_value}"
            
            doc += "\n"
            
            # Add constraints
            details = []
            if constraint.min_value is not None:
                details.append(f"min: {constraint.min_value}")
            if constraint.max_value is not None:
                details.append(f"max: {constraint.max_value}")
            if constraint.min_length is not None:
                details.append(f"min_length: {constraint.min_length}")
            if constraint.max_length is not None:
                details.append(f"max_length: {constraint.max_length}")
            if constraint.allowed_values:
                details.append(f"allowed: {constraint.allowed_values}")
            
            if details:
                doc += f"{spaces}  Constraints: {', '.join(details)}\n"
            
            # Nested schema
            if constraint.schema:
                doc += f"{spaces}  Fields:\n"
                for nested_name, nested_constraint in constraint.schema.items():
                    doc += document_constraint(nested_name, nested_constraint, indent + 2)
            
            return doc
        
        documentation = "Vehicle Control Configuration Schema\n"
        documentation += "=" * 40 + "\n\n"
        
        for param_name, constraint in self.schema.items():
            documentation += document_constraint(param_name, constraint)
            documentation += "\n"
        
        return documentation