#!/usr/bin/env python3
"""Script to create a new client."""
import sys
import argparse
from uuid import uuid4

from app.core.security import hash_password
from app.db.session import get_session_local, get_engine
from app.db.models import Base, Client
from app.core.config import settings

# Get engine and session
engine = get_engine()
SessionLocal = get_session_local()


def create_client(machine_id: str, password: str, metadata: dict = None):
    """Create a new client."""
    db = SessionLocal()
    
    try:
        # Check if client already exists
        existing = db.query(Client).filter(Client.machine_id == machine_id).first()
        if existing:
            print(f"Client with machine_id '{machine_id}' already exists!")
            return
        
        # Create new client
        client = Client(
            id=uuid4(),
            machine_id=machine_id,
            password_hash=hash_password(password),
            is_active=True,
            client_metadata=metadata or {},
        )
        
        db.add(client)
        db.commit()
        
        print(f"Created client:")
        print(f"  ID: {client.id}")
        print(f"  Machine ID: {client.machine_id}")
        print(f"  Active: {client.is_active}")
        
    except Exception as e:
        db.rollback()
        print(f"Error creating client: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new client")
    parser.add_argument("--machine-id", required=True, help="Machine identifier")
    parser.add_argument("--password", required=True, help="Client password")
    parser.add_argument("--metadata", help="JSON metadata")
    
    args = parser.parse_args()
    
    metadata = {}
    if args.metadata:
        import json
        metadata = json.loads(args.metadata)
    
    create_client(args.machine_id, args.password, metadata)

