#!/usr/bin/env python3
"""Script to clear Neo4j database indexes and constraints using direct Neo4j connection."""

from neo4j import GraphDatabase
from settings import settings
import sys


def get_neo4j_driver():
    """Get Neo4j driver."""
    return GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )


def execute_cypher(driver, query, parameters=None):
    """Execute a Cypher query."""
    with driver.session() as session:
        result = session.run(query, parameters or {})
        return [record.data() for record in result]


def clear_indexes_only():
    """Clear only indexes, keeping data and constraints."""
    driver = get_neo4j_driver()
    
    try:
        print("🔍 Dropping all indexes...")
        
        # Get all indexes
        indexes = execute_cypher(driver, "SHOW INDEXES")
        print(f"Found {len(indexes)} indexes to process")
        
        for idx in indexes:
            index_name = idx.get('name')
            # Skip system indexes
            if index_name and index_name not in ['range_index_provider_2.0', 'text_index_provider_2.0', 'point_index_provider_2.0']:
                try:
                    execute_cypher(driver, f"DROP INDEX {index_name}")
                    print(f"✅ Dropped index: {index_name}")
                except Exception as e:
                    print(f"⚠️ Could not drop index {index_name}: {e}")
        
        # Verify
        remaining_indexes = execute_cypher(driver, "SHOW INDEXES")
        user_indexes = [idx for idx in remaining_indexes if idx.get('name') not in ['range_index_provider_2.0', 'text_index_provider_2.0', 'point_index_provider_2.0']]
        print(f"\n📊 Remaining user indexes: {len(user_indexes)}")
        
        if len(user_indexes) == 0:
            print("🎉 All user indexes successfully dropped!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        driver.close()


def clear_constraints_only():
    """Clear only constraints, keeping data and indexes."""
    driver = get_neo4j_driver()
    
    try:
        print("🔍 Dropping all constraints...")
        
        # Get all constraints
        constraints = execute_cypher(driver, "SHOW CONSTRAINTS")
        print(f"Found {len(constraints)} constraints to process")
        
        for constraint in constraints:
            constraint_name = constraint.get('name')
            if constraint_name:
                try:
                    execute_cypher(driver, f"DROP CONSTRAINT {constraint_name}")
                    print(f"✅ Dropped constraint: {constraint_name}")
                except Exception as e:
                    print(f"⚠️ Could not drop constraint {constraint_name}: {e}")
        
        # Verify
        remaining_constraints = execute_cypher(driver, "SHOW CONSTRAINTS")
        print(f"\n🔒 Remaining constraints: {len(remaining_constraints)}")
        
        if len(remaining_constraints) == 0:
            print("🎉 All constraints successfully dropped!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        driver.close()


def clear_data_only():
    """Clear only data, keeping indexes and constraints."""
    driver = get_neo4j_driver()
    
    try:
        print("🔍 Deleting all nodes and relationships...")
        
        # Count current nodes
        node_count = execute_cypher(driver, "MATCH (n) RETURN count(n) as count")[0]['count']
        print(f"Found {node_count} nodes to delete")
        
        if node_count > 0:
            # Delete all data
            execute_cypher(driver, "MATCH (n) DETACH DELETE n")
            print("✅ All data deleted")
            
            # Verify
            final_count = execute_cypher(driver, "MATCH (n) RETURN count(n) as count")[0]['count']
            print(f"📈 Remaining nodes: {final_count}")
            
            if final_count == 0:
                print("🎉 All data successfully deleted!")
        else:
            print("ℹ️ Database is already empty")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        driver.close()


def clear_everything():
    """Clear indexes, constraints, and data."""
    driver = get_neo4j_driver()
    
    try:
        print("🔍 Checking current database state...")
        
        # Show current state
        indexes = execute_cypher(driver, "SHOW INDEXES")
        constraints = execute_cypher(driver, "SHOW CONSTRAINTS")
        node_count = execute_cypher(driver, "MATCH (n) RETURN count(n) as count")[0]['count']
        
        user_indexes = [idx for idx in indexes if idx.get('name') not in ['range_index_provider_2.0', 'text_index_provider_2.0', 'point_index_provider_2.0']]
        
        print(f"📊 User indexes: {len(user_indexes)}")
        print(f"🔒 Constraints: {len(constraints)}")
        print(f"📈 Nodes: {node_count}")
        
        print("\n🧹 Starting complete cleanup...")
        
        # Step 1: Delete all data
        if node_count > 0:
            print("1️⃣ Deleting all nodes and relationships...")
            execute_cypher(driver, "MATCH (n) DETACH DELETE n")
            print("   ✅ All data deleted")
        
        # Step 2: Drop all constraints
        if constraints:
            print("2️⃣ Dropping all constraints...")
            for constraint in constraints:
                constraint_name = constraint.get('name')
                if constraint_name:
                    try:
                        execute_cypher(driver, f"DROP CONSTRAINT {constraint_name}")
                        print(f"   ✅ Dropped constraint: {constraint_name}")
                    except Exception as e:
                        print(f"   ⚠️ Could not drop constraint {constraint_name}: {e}")
        
        # Step 3: Drop all user indexes
        if user_indexes:
            print("3️⃣ Dropping all user indexes...")
            for idx in user_indexes:
                index_name = idx.get('name')
                try:
                    execute_cypher(driver, f"DROP INDEX {index_name}")
                    print(f"   ✅ Dropped index: {index_name}")
                except Exception as e:
                    print(f"   ⚠️ Could not drop index {index_name}: {e}")
        
        print("\n🔍 Verifying cleanup...")
        
        # Final verification
        final_indexes = execute_cypher(driver, "SHOW INDEXES")
        final_constraints = execute_cypher(driver, "SHOW CONSTRAINTS")
        final_nodes = execute_cypher(driver, "MATCH (n) RETURN count(n) as count")[0]['count']
        
        final_user_indexes = [idx for idx in final_indexes if idx.get('name') not in ['range_index_provider_2.0', 'text_index_provider_2.0', 'point_index_provider_2.0']]
        
        print(f"📊 Remaining user indexes: {len(final_user_indexes)}")
        print(f"🔒 Remaining constraints: {len(final_constraints)}")
        print(f"📈 Remaining nodes: {final_nodes}")
        
        if len(final_user_indexes) == 0 and len(final_constraints) == 0 and final_nodes == 0:
            print("\n🎉 Database completely cleared!")
        else:
            print("\n⚠️ Some items may still remain")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        driver.close()


def show_database_state():
    """Show current database state."""
    driver = get_neo4j_driver()
    
    try:
        print("🔍 Current database state:")
        
        # Show indexes
        indexes = execute_cypher(driver, "SHOW INDEXES")
        user_indexes = [idx for idx in indexes if idx.get('name') not in ['range_index_provider_2.0', 'text_index_provider_2.0', 'point_index_provider_2.0']]
        
        print(f"\n📊 User Indexes ({len(user_indexes)}):")
        for idx in user_indexes:
            print(f"  - {idx.get('name', 'Unknown')}: {idx.get('type', 'Unknown type')}")
        
        # Show constraints
        constraints = execute_cypher(driver, "SHOW CONSTRAINTS")
        print(f"\n🔒 Constraints ({len(constraints)}):")
        for constraint in constraints:
            print(f"  - {constraint.get('name', 'Unknown')}: {constraint.get('type', 'Unknown type')}")
        
        # Show node count
        node_count = execute_cypher(driver, "MATCH (n) RETURN count(n) as count")[0]['count']
        print(f"\n📈 Total nodes: {node_count}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        driver.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "indexes":
            clear_indexes_only()
        elif command == "constraints":
            clear_constraints_only()
        elif command == "data":
            clear_data_only()
        elif command == "all":
            clear_everything()
        elif command == "status":
            show_database_state()
        else:
            print("Usage: python clear_neo4j_indexes.py [indexes|constraints|data|all|status]")
    else:
        print("What would you like to clear?")
        print("1. Indexes only")
        print("2. Constraints only")
        print("3. Data only")
        print("4. Everything (indexes, constraints, and data)")
        print("5. Show current state")
        choice = input("Enter choice (1-5): ").strip()
        
        if choice == "1":
            clear_indexes_only()
        elif choice == "2":
            clear_constraints_only()
        elif choice == "3":
            clear_data_only()
        elif choice == "4":
            clear_everything()
        elif choice == "5":
            show_database_state()
        else:
            print("Invalid choice") 