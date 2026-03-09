#!/usr/bin/env python3
"""
Force-apply new default weights to the active model in database.
Run this after changing DEFAULT_WEIGHTS to apply immediately.
"""
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from src.db.session import AsyncSessionLocal
from src.engine.scoring import DEFAULT_WEIGHTS


async def force_weights():
    """Update the active model's weights with new defaults."""
    import json

    print("New weights to apply:")
    for name, weight in sorted(DEFAULT_WEIGHTS.items(), key=lambda x: -x[1]):
        print(f"  {name}: {weight:.2%}")
    print()

    async with AsyncSessionLocal() as db:
        # Get current active version
        result = await db.execute(text("""
            SELECT id, version, weights, performance
            FROM signal_weights
            WHERE is_active = TRUE
            ORDER BY created_at DESC
            LIMIT 1
        """))
        row = result.fetchone()

        if not row:
            print("No active model found. Creating new one...")
            # Insert new weights as version 1
            await db.execute(text("""
                INSERT INTO signal_weights (id, version, weights, is_active, performance, created_at)
                VALUES (gen_random_uuid(), 1, :weights, TRUE, :performance, NOW())
            """), {
                "weights": json.dumps(DEFAULT_WEIGHTS),
                "performance": json.dumps({"forced": True, "note": "Force-applied from script"})
            })
            await db.commit()
            print("Created new active model with forced weights.")
        else:
            old_weights = row[2]
            version = row[1]
            performance = row[3] or {}

            print(f"Current active model: v{version}")
            print("Old weights:")
            for name, weight in sorted(old_weights.items(), key=lambda x: -x[1]):
                new_w = DEFAULT_WEIGHTS.get(name, 0)
                delta = new_w - weight
                marker = "←" if abs(delta) > 0.01 else ""
                print(f"  {name}: {weight:.2%} → {new_w:.2%} {marker}")

            # Check for new signals not in old weights
            for name in DEFAULT_WEIGHTS:
                if name not in old_weights:
                    print(f"  {name}: NEW → {DEFAULT_WEIGHTS[name]:.2%} ←")

            print()
            confirm = input("Apply these weights? [y/N]: ").strip().lower()
            if confirm != 'y':
                print("Aborted.")
                return

            # Update the weights
            performance["forced"] = True
            performance["forced_at"] = str(asyncio.get_event_loop().time())

            await db.execute(text("""
                UPDATE signal_weights
                SET weights = :weights, performance = :performance
                WHERE id = :id
            """), {
                "id": row[0],
                "weights": json.dumps(DEFAULT_WEIGHTS),
                "performance": json.dumps(performance)
            })
            await db.commit()
            print(f"✓ Updated v{version} with new weights!")


if __name__ == "__main__":
    asyncio.run(force_weights())
