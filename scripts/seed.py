#!/usr/bin/env python3
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import init_db, get_db

def run_seed():
    print("Initializing database tables and indexes...")
    init_db()

    print("Seeding demo tenants and widgets...")
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Tenants
        tenants = [
            ("tenant_acme", "Acme Corporation", "demo_key_acme_123"),
            ("tenant_beta", "Beta Innovations", "demo_key_beta_456"),
        ]
        for t_id, t_name, t_key in tenants:
            cursor.execute(
                "INSERT OR REPLACE INTO tenants (id, name, api_key) VALUES (?, ?, ?)",
                (t_id, t_name, t_key)
            )

        # 2. Widgets for Acme
        acme_fields_1 = json.dumps([
            {"name": "name", "label": "Full Name", "type": "text", "required": True, "placeholder": "Jane Doe"},
            {"name": "email", "label": "Work Email", "type": "email", "required": True, "placeholder": "jane@company.com"}
        ])
        acme_theme_1 = json.dumps({"primary_color": "#4F46E5", "position": "inline", "theme": "light"})

        cursor.execute(
            """
            INSERT OR REPLACE INTO widgets (
                id, tenant_id, name, type, title, description, fields_schema, button_text, display_theme, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wgt_demo_newsletter",
                "tenant_acme",
                "Developer Newsletter Signup",
                "signup",
                "Subscribe to Acme Tech Brief",
                "Join 50,000+ engineers receiving our weekly architectural deep dives.",
                acme_fields_1,
                "Subscribe Now",
                acme_theme_1,
                1
            )
        )

        acme_fields_2 = json.dumps([
            {"name": "email", "label": "Your Email", "type": "email", "required": True, "placeholder": "you@domain.com"},
            {"name": "message", "label": "How can we help?", "type": "textarea", "required": True, "placeholder": "Tell us about your project..."}
        ])
        acme_theme_2 = json.dumps({"primary_color": "#059669", "position": "bottom-right", "theme": "light"})

        cursor.execute(
            """
            INSERT OR REPLACE INTO widgets (
                id, tenant_id, name, type, title, description, fields_schema, button_text, display_theme, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wgt_demo_support",
                "tenant_acme",
                "Customer Support Popover",
                "cta_popover",
                "Need Help with Integration?",
                "Our team typically answers in under 15 minutes.",
                acme_fields_2,
                "Send Message",
                acme_theme_2,
                1
            )
        )

        # 3. Widget for Beta (to prove tenant isolation)
        beta_fields = json.dumps([
            {"name": "email", "label": "Email", "type": "email", "required": True, "placeholder": "founder@startup.io"},
            {"name": "company", "label": "Company Name", "type": "text", "required": False, "placeholder": "Startup Inc."}
        ])
        beta_theme = json.dumps({"primary_color": "#D97706", "position": "inline", "theme": "light"})

        cursor.execute(
            """
            INSERT OR REPLACE INTO widgets (
                id, tenant_id, name, type, title, description, fields_schema, button_text, display_theme, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wgt_beta_contact",
                "tenant_beta",
                "Beta Private Waitlist",
                "signup",
                "Beta Innovations Early Access",
                "Request exclusive access to our upcoming API.",
                beta_fields,
                "Request Invite",
                beta_theme,
                1
            )
        )

        # 4. Seed sample submissions for Acme
        sample_submissions = [
            ("sub_sample_1", "wgt_demo_newsletter", "tenant_acme", json.dumps({"name": "Alice Johnson", "email": "alice@gmail.com"}), "8.8.8.8", "United States", "Mountain View", "California", "ip-api.com"),
            ("sub_sample_2", "wgt_demo_newsletter", "tenant_acme", json.dumps({"name": "Bob Smith", "email": "bob@techcorp.co"}), "1.1.1.1", "Australia", "Sydney", "New South Wales", "ip-api.com"),
            ("sub_sample_3", "wgt_demo_newsletter", "tenant_acme", json.dumps({"name": "Carlos Gomez", "email": "carlos@madrid.es"}), "212.51.177.1", "Spain", "Madrid", "Madrid", "ipapi.co"),
            ("sub_sample_4", "wgt_demo_support", "tenant_acme", json.dumps({"email": "dev@partner.com", "message": "Loving the widget API!"}), "103.21.244.0", "India", "Bengaluru", "Karnataka", "ip-api.com"),
            ("sub_sample_5", "wgt_beta_contact", "tenant_beta", json.dumps({"email": "clara@beta-invest.org", "company": "Beta Capital"}), "185.199.108.153", "United Kingdom", "London", "England", "ip-api.com"),
        ]

        for s_id, w_id, t_id, payload, ip, country, city, region, provider in sample_submissions:
            cursor.execute(
                """
                INSERT OR REPLACE INTO submissions (
                    id, widget_id, tenant_id, payload, ip_address, country, city, region, geo_provider
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (s_id, w_id, t_id, payload, ip, country, city, region, provider)
            )

    print("Database seeding completed successfully!")
    print("Tenants configured:")
    print(" - Acme Corp: API Key = demo_key_acme_123 (Widgets: wgt_demo_newsletter, wgt_demo_support)")
    print(" - Beta Innovations: API Key = demo_key_beta_456 (Widget: wgt_beta_contact)")

if __name__ == "__main__":
    run_seed()
