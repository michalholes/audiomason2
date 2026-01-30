#!/usr/bin/env python3
"""
Test script for AudioMason v2 Web UI Extensions

Tests all new API endpoints to ensure proper functionality.
"""

import requests
import json
from pathlib import Path

BASE_URL = "http://localhost:8080"

def test_plugin_endpoints():
    """Test plugin management endpoints."""
    print("\n" + "="*60)
    print("TESTING PLUGIN ENDPOINTS")
    print("="*60)
    
    # Test 1: List plugins
    print("\n[TEST 1] GET /api/plugins")
    response = requests.get(f"{BASE_URL}/api/plugins")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        plugins = response.json()
        print(f"Found {len(plugins)} plugins")
        if plugins:
            print(f"First plugin: {plugins[0]['name']}")
    else:
        print(f"Error: {response.text}")
    
    # Test 2: Get plugin details (if any exist)
    if response.status_code == 200 and plugins:
        plugin_name = plugins[0]['name']
        print(f"\n[TEST 2] GET /api/plugins/{plugin_name}")
        response = requests.get(f"{BASE_URL}/api/plugins/{plugin_name}")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            plugin = response.json()
            print(f"Plugin: {plugin['name']} v{plugin['version']}")
            print(f"Enabled: {plugin['enabled']}")
        else:
            print(f"Error: {response.text}")
        
        # Test 3: Disable plugin
        print(f"\n[TEST 3] PUT /api/plugins/{plugin_name}/disable")
        response = requests.put(f"{BASE_URL}/api/plugins/{plugin_name}/disable")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test 4: Enable plugin
        print(f"\n[TEST 4] PUT /api/plugins/{plugin_name}/enable")
        response = requests.put(f"{BASE_URL}/api/plugins/{plugin_name}/enable")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

def test_wizard_endpoints():
    """Test wizard management endpoints."""
    print("\n" + "="*60)
    print("TESTING WIZARD ENDPOINTS")
    print("="*60)
    
    # Test 1: List wizards
    print("\n[TEST 1] GET /api/wizards")
    response = requests.get(f"{BASE_URL}/api/wizards")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        wizards = response.json()
        print(f"Found {len(wizards)} wizards")
        if wizards:
            print(f"First wizard: {wizards[0]['name']}")
    else:
        print(f"Error: {response.text}")
    
    # Test 2: Create wizard
    print("\n[TEST 2] POST /api/wizards")
    test_wizard = {
        "wizard": {
            "name": "Test Wizard",
            "description": "A test wizard created by the test script",
            "steps": [
                {
                    "id": "step1",
                    "type": "input",
                    "prompt": "Enter test value",
                    "required": True
                }
            ]
        }
    }
    response = requests.post(
        f"{BASE_URL}/api/wizards",
        json=test_wizard,
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Test 3: Get wizard (if created)
    if response.status_code == 200:
        result = response.json()
        wizard_name = result.get('filename', 'test_wizard')
        
        print(f"\n[TEST 3] GET /api/wizards/{wizard_name}")
        response = requests.get(f"{BASE_URL}/api/wizards/{wizard_name}")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            wizard = response.json()
            print(f"Wizard loaded: {wizard.get('wizard', {}).get('name')}")
        
        # Test 4: Delete wizard
        print(f"\n[TEST 4] DELETE /api/wizards/{wizard_name}")
        response = requests.delete(f"{BASE_URL}/api/wizards/{wizard_name}")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

def test_config_endpoints():
    """Test configuration management endpoints."""
    print("\n" + "="*60)
    print("TESTING CONFIG ENDPOINTS")
    print("="*60)
    
    # Test 1: Get config schema
    print("\n[TEST 1] GET /api/config/schema")
    response = requests.get(f"{BASE_URL}/api/config/schema")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        schema = response.json()
        print(f"Schema keys: {', '.join(schema.keys())}")
    else:
        print(f"Error: {response.text}")
    
    # Test 2: Get current config
    print("\n[TEST 2] GET /api/config")
    response = requests.get(f"{BASE_URL}/api/config")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        config = response.json()
        print(f"Config keys: {', '.join(config.keys())}")
        print(f"Current bitrate: {config.get('bitrate', {}).get('value')}")
    else:
        print(f"Error: {response.text}")
    
    # Test 3: Update config (non-destructive change)
    print("\n[TEST 3] PUT /api/config")
    current_config = response.json() if response.status_code == 200 else {}
    test_update = {
        "bitrate": "192k"  # Temporary change
    }
    response = requests.put(
        f"{BASE_URL}/api/config",
        json=test_update,
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Restore original value
    if current_config:
        original_bitrate = current_config.get('bitrate', {}).get('value')
        if original_bitrate:
            print(f"\nRestoring original bitrate: {original_bitrate}")
            requests.put(
                f"{BASE_URL}/api/config",
                json={"bitrate": original_bitrate},
                headers={"Content-Type": "application/json"}
            )

def test_status_endpoint():
    """Test basic status endpoint."""
    print("\n" + "="*60)
    print("TESTING STATUS ENDPOINT")
    print("="*60)
    
    print("\n[TEST] GET /api/status")
    response = requests.get(f"{BASE_URL}/api/status")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        status = response.json()
        print(f"System status: {status['status']}")
        print(f"Active jobs: {status['active_jobs']}")
        print(f"Version: {status['version']}")
    else:
        print(f"Error: {response.text}")

def main():
    """Run all tests."""
    print("="*60)
    print("AudioMason v2 - Web UI Extensions Test Suite")
    print("="*60)
    print(f"\nTesting server at: {BASE_URL}")
    print("\nNOTE: Make sure the web server is running before running tests!")
    print("      Start it with: python -m plugins.web_server.plugin")
    
    try:
        # Test if server is running
        response = requests.get(f"{BASE_URL}/api/status", timeout=5)
        if response.status_code != 200:
            print("\n❌ Server not responding properly!")
            return
    except requests.exceptions.ConnectionError:
        print("\n❌ Cannot connect to server! Is it running?")
        return
    except Exception as e:
        print(f"\n❌ Error connecting to server: {e}")
        return
    
    print("\n✅ Server is running!")
    
    # Run tests
    try:
        test_status_endpoint()
        test_plugin_endpoints()
        test_wizard_endpoints()
        test_config_endpoints()
        
        print("\n" + "="*60)
        print("ALL TESTS COMPLETED")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
