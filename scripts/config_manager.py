#!/usr/bin/env python3
"""
AST-Grep MCP Configuration Manager

This script provides command-line utilities for managing AST-Grep MCP server configuration.
"""

import argparse
import sys
import json
from pathlib import Path
from typing import Optional

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ast_grep_mcp.config import (
    ConfigurationManager, ConfigurationError, EnvironmentType,
    load_configuration, get_configuration
)
from ast_grep_mcp.config_migration import (
    ConfigurationMigrator, migrate_legacy_configuration
)


def create_template(environment: str, output_path: str):
    """Create configuration template for environment."""
    try:
        env_type = EnvironmentType(environment.lower())
        output_file = Path(output_path)
        
        manager = ConfigurationManager()
        success = manager.create_environment_template(env_type, output_file)
        
        if success:
            print(f"✅ Created {environment} configuration template: {output_file}")
        else:
            print(f"❌ Failed to create configuration template")
            sys.exit(1)
            
    except ValueError:
        print(f"❌ Invalid environment type: {environment}")
        print(f"Valid options: {', '.join([e.value for e in EnvironmentType])}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error creating template: {e}")
        sys.exit(1)


def validate_config(config_path: Optional[str] = None):
    """Validate configuration file."""
    try:
        manager = ConfigurationManager()
        
        if config_path:
            config = manager.load_configuration(Path(config_path))
        else:
            config = manager.get_configuration()
        
        validation = manager.validate_configuration(config)
        
        if validation['valid']:
            print("✅ Configuration is valid")
        else:
            print("❌ Configuration validation failed")
            
        if validation['errors']:
            print("\nErrors:")
            for error in validation['errors']:
                print(f"  • {error}")
                
        if validation['warnings']:
            print("\nWarnings:")
            for warning in validation['warnings']:
                print(f"  • {warning}")
                
        if validation['info']:
            print("\nInfo:")
            for info in validation['info']:
                print(f"  • {info}")
        
        sys.exit(0 if validation['valid'] else 1)
        
    except Exception as e:
        print(f"❌ Validation error: {e}")
        sys.exit(1)


def export_config(config_path: str, output_path: str, format_type: str = "yaml"):
    """Export configuration to specified format."""
    try:
        manager = ConfigurationManager()
        config = manager.load_configuration(Path(config_path))
        
        success = manager.export_configuration(Path(output_path), format_type)
        
        if success:
            print(f"✅ Configuration exported to {output_path} ({format_type})")
        else:
            print(f"❌ Failed to export configuration")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Export error: {e}")
        sys.exit(1)


def migrate_config(output_path: Optional[str] = None):
    """Migrate legacy environment-based configuration."""
    try:
        migrator = ConfigurationMigrator()
        
        output_file = Path(output_path) if output_path else None
        new_config = migrator.migrate_from_legacy(output_file)
        
        # Generate migration report
        from ast_grep_mcp.config_migration import LegacyServerConfig
        legacy_config = LegacyServerConfig()
        report = migrator.generate_migration_report(legacy_config, new_config)
        
        print("🔄 Configuration migration completed")
        print()
        print(report)
        
        if output_file:
            print(f"\n✅ Migrated configuration saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        sys.exit(1)


def show_config(config_path: Optional[str] = None):
    """Display current configuration."""
    try:
        manager = ConfigurationManager()
        
        if config_path:
            config = manager.load_configuration(Path(config_path))
        else:
            config = manager.get_configuration()
        
        print("📋 Current Configuration:")
        print("=" * 50)
        
        # Basic info
        print(f"Name: {config.name}")
        print(f"Version: {config.version}")
        print(f"Environment: {config.environment.value}")
        print(f"Debug Mode: {config.debug}")
        print()
        
        # Security
        print("🔒 Security:")
        print(f"  Enabled: {config.security.enable_security}")
        print(f"  Rate Limiting: {config.security.enable_rate_limiting}")
        print(f"  Input Validation: {config.security.enable_input_validation}")
        print()
        
        # Performance
        print("⚡ Performance:")
        print(f"  Monitoring: {config.performance.enable_performance}")
        print(f"  Caching: {config.performance.enable_caching}")
        print(f"  Memory Warning: {config.performance.memory_warning_threshold}%")
        print(f"  CPU Warning: {config.performance.cpu_warning_threshold}%")
        print()
        
        # Logging
        print("📝 Logging:")
        print(f"  Level: {config.logging.log_level.value}")
        print(f"  Format: {config.logging.log_format.value}")
        print(f"  File Logging: {config.logging.enable_file_logging}")
        if config.logging.log_file_path:
            print(f"  File Path: {config.logging.log_file_path}")
        print()
        
        # AST-Grep
        print("🔍 AST-Grep:")
        print(f"  Auto-detect Binary: {config.ast_grep.auto_detect_binary}")
        if config.ast_grep.ast_grep_path:
            print(f"  Binary Path: {config.ast_grep.ast_grep_path}")
        print(f"  Default Timeout: {config.ast_grep.default_timeout}s")
        print(f"  Max Results: {config.ast_grep.max_results}")
        
    except Exception as e:
        print(f"❌ Error displaying configuration: {e}")
        sys.exit(1)


def check_health():
    """Check configuration system health."""
    try:
        print("🏥 Configuration System Health Check")
        print("=" * 40)
        
        # Check if configuration can be loaded
        try:
            manager = ConfigurationManager()
            config = manager.get_configuration()
            print("✅ Configuration loading: OK")
        except Exception as e:
            print(f"❌ Configuration loading: FAILED - {e}")
            return False
        
        # Validate configuration
        try:
            validation = manager.validate_configuration(config)
            if validation['valid']:
                print("✅ Configuration validation: OK")
            else:
                print("⚠️  Configuration validation: ISSUES FOUND")
                for error in validation['errors']:
                    print(f"    • {error}")
        except Exception as e:
            print(f"❌ Configuration validation: FAILED - {e}")
            return False
        
        # Check dependencies
        try:
            import yaml
            print("✅ YAML support: OK")
        except ImportError:
            print("❌ YAML support: MISSING")
            return False
        
        try:
            import pydantic
            print("✅ Pydantic validation: OK")
        except ImportError:
            print("❌ Pydantic validation: MISSING")
            return False
        
        try:
            from cryptography.fernet import Fernet
            print("✅ Cryptography support: OK")
        except ImportError:
            print("⚠️  Cryptography support: MISSING (secrets encryption disabled)")
        
        print("\n🎉 Configuration system is healthy!")
        return True
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


def list_templates():
    """List available configuration templates."""
    print("📄 Available Configuration Templates:")
    print("=" * 40)
    
    templates_dir = Path(__file__).parent.parent / "config"
    
    if templates_dir.exists():
        for template_file in templates_dir.glob("*.yaml"):
            print(f"  • {template_file.name} - {template_file.stem.title()} environment")
    else:
        print("  No templates found in config/ directory")
    
    print("\nTo create a custom template:")
    print("  python config_manager.py create-template <environment> <output_path>")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AST-Grep MCP Configuration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create development configuration template
  python config_manager.py create-template development my-config.yaml
  
  # Validate configuration
  python config_manager.py validate --config my-config.yaml
  
  # Migrate from legacy environment variables
  python config_manager.py migrate --output migrated-config.yaml
  
  # Show current configuration
  python config_manager.py show --config my-config.yaml
  
  # Export configuration to JSON
  python config_manager.py export my-config.yaml output.json --format json
  
  # Check system health
  python config_manager.py health
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create template command
    create_parser = subparsers.add_parser('create-template', help='Create configuration template')
    create_parser.add_argument('environment', choices=[e.value for e in EnvironmentType],
                              help='Environment type')
    create_parser.add_argument('output', help='Output file path')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate configuration')
    validate_parser.add_argument('--config', help='Configuration file path')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export configuration')
    export_parser.add_argument('config', help='Configuration file path')
    export_parser.add_argument('output', help='Output file path')
    export_parser.add_argument('--format', choices=['yaml', 'json'], default='yaml',
                              help='Output format')
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Migrate legacy configuration')
    migrate_parser.add_argument('--output', help='Output file path')
    
    # Show command
    show_parser = subparsers.add_parser('show', help='Show configuration')
    show_parser.add_argument('--config', help='Configuration file path')
    
    # Health command
    subparsers.add_parser('health', help='Check configuration system health')
    
    # List templates command
    subparsers.add_parser('list-templates', help='List available templates')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute commands
    if args.command == 'create-template':
        create_template(args.environment, args.output)
    elif args.command == 'validate':
        validate_config(args.config)
    elif args.command == 'export':
        export_config(args.config, args.output, args.format)
    elif args.command == 'migrate':
        migrate_config(args.output)
    elif args.command == 'show':
        show_config(args.config)
    elif args.command == 'health':
        success = check_health()
        sys.exit(0 if success else 1)
    elif args.command == 'list-templates':
        list_templates()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main() 