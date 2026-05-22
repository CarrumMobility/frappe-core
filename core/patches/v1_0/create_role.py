"""Create Roles and assign permissions to them"""

import frappe


def execute():
    roles = ['hub_manager', 'Telecaller', 'Telecaller Lead', 'driver', 'driver_manager', 'Onboarding']
    role_permissions = {
        "hub_manager": {
                "tabCRM Lead": ["create", "read","select","write"],
                "tabCall Session": ["create", "read", "select", "write"],
                "tabCall Log": ["create", "read", "select", "write"],
                "tabCRM Lead Status": ["create", "read", "select", "write"],
                "FCRM Note": ["create", "read", "select", "write"],
                "FCRM Event": ["create", "read", "select", "write"],
                "FCRM Settings": ["read", "select"],
                "User dialer session logs": ['read', 'select'],
                "payment_logs": ['read', 'select']
            },
        "Telecaller": {
            "tabCRM Lead": ["create", "read", "write"]
        },
        "Telecaller Lead": {
            "tabCRM Lead": ["create", "read", "write"]
        },
        "Onboarding": {
            "tabCRM Lead": ["create", "read", "write"]
        },
        "driver": {
            "tabCRM Lead": ["create", "read", "write"]
        },
        "driver_manager": {
            "tabCRM Lead": ["create", "read", "write"]
        }
    }

    # create role and assign their permission against role
    for role in roles:
        print(role)
        print(role_permissions[role])