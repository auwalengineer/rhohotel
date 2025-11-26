"""
Hotel Room Type Information Module
Retrieves room type details including amenities, images, and specifications
EXCLUDES: Pricing, availability checks, booking logic
"""

import frappe


@frappe.whitelist(allow_guest=True)
def get_all_room_types():
    """
    Get all active room types with complete details.
    
    Returns:
        dict: All room types with their amenities, images, and specifications
    """
    try:
        # Get all active room types - only fields that exist in your schema
        room_types = frappe.get_all(
            "Hotel Room Type",
            filters={"is_active": 1},
            fields=[
                "name",
                "room_type",
                "capacity",
                "extra_bed_capacity",
                "base_adult",
                "max_adult",
                "base_child",
                "max_child",
                "is_active"
            ]
        )
        
        if not room_types:
            return {
                "success": False,
                "message": "No active room types found",
                "room_types": []
            }
        
        # Enrich each room type with amenities and images
        enriched_room_types = []
        for room_type in room_types:
            details = get_room_type_complete_details(room_type["name"])
            enriched_room_types.append(details)
        
        return {
            "success": True,
            "total_room_types": len(enriched_room_types),
            "room_types": enriched_room_types
        }
    
    except Exception as e:
        frappe.log_error(f"Error fetching room types: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=True)
def get_room_type_info(room_type):
    """
    Get detailed information about a specific room type.
    
    Args:
        room_type (str): Room Type name
    
    Returns:
        dict: Complete room type details with amenities and images
    """
    try:
        details = get_room_type_complete_details(room_type)
        return {
            "success": True,
            "room_type": details
        }
    except frappe.DoesNotExistError:
        return {
            "success": False,
            "error": f"Room type '{room_type}' not found"
        }
    except Exception as e:
        frappe.log_error(f"Error fetching room type info: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def get_room_type_complete_details(room_type_name):
    """
    Get complete details for a room type including amenities, images, and inventory.
    
    Args:
        room_type_name (str): Room Type name
    
    Returns:
        dict: Room type details with amenities, images, and inventory
    """
    # Get room type document
    room_type_doc = frappe.get_doc("Hotel Room Type", room_type_name)
    
    # Extract amenities
    amenities = []
    if hasattr(room_type_doc, 'amenities') and room_type_doc.amenities:
        for amenity in room_type_doc.amenities:
            amenities.append({
                "item": amenity.item
            })
    
    # Extract images
    images = []
    if hasattr(room_type_doc, 'hotel_room_images') and room_type_doc.hotel_room_images:
        for img in room_type_doc.hotel_room_images:
            image_data = {
                "image": img.image
            }
            if img.caption:
                image_data["caption"] = img.caption
            images.append(image_data)
    
    # Extract standard inventory
    standard_inventory = []
    if hasattr(room_type_doc, 'standard_inventory') and room_type_doc.standard_inventory:
        for inv_item in room_type_doc.standard_inventory:
            standard_inventory.append({
                "item": inv_item.item,
                "quantity": inv_item.quantity
            })
    
    # Build response - only fields that exist in your schema
    details = {
        "name": room_type_doc.name,
        "room_type": room_type_doc.room_type,
        "capacity": room_type_doc.capacity or 0,
        "extra_bed_capacity": room_type_doc.extra_bed_capacity or 0,
        "base_adult": room_type_doc.base_adult or 1,
        "max_adult": room_type_doc.max_adult or 0,
        "base_child": room_type_doc.base_child or 0,
        "max_child": room_type_doc.max_child or 0,
        "is_active": room_type_doc.is_active,
        "amenities": amenities,
        "images": images,
        "standard_inventory": standard_inventory,
        "total_amenities": len(amenities),
        "total_images": len(images),
        "total_inventory_items": len(standard_inventory)
    }
    
    return details


@frappe.whitelist(allow_guest=True)
def get_room_type_amenities(room_type):
    """
    Get only amenities for a specific room type.
    
    Args:
        room_type (str): Room Type name
    
    Returns:
        dict: Amenities list
    """
    try:
        room_type_doc = frappe.get_doc("Hotel Room Type", room_type)
        
        amenities = []
        if hasattr(room_type_doc, 'amenities') and room_type_doc.amenities:
            for amenity in room_type_doc.amenities:
                amenities.append({
                    "item": amenity.item
                })
        
        return {
            "success": True,
            "room_type": room_type,
            "total_amenities": len(amenities),
            "amenities": amenities
        }
    
    except frappe.DoesNotExistError:
        return {
            "success": False,
            "error": f"Room type '{room_type}' not found"
        }
    except Exception as e:
        frappe.log_error(f"Error fetching amenities: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=True)
def get_room_type_images(room_type):
    """
    Get only images for a specific room type.
    
    Args:
        room_type (str): Room Type name
    
    Returns:
        dict: Images list
    """
    try:
        room_type_doc = frappe.get_doc("Hotel Room Type", room_type)
        
        images = []
        if hasattr(room_type_doc, 'hotel_room_images') and room_type_doc.hotel_room_images:
            for img in room_type_doc.hotel_room_images:
                image_data = {
                    "image": img.image
                }
                if img.caption:
                    image_data["caption"] = img.caption
                images.append(image_data)
        
        return {
            "success": True,
            "room_type": room_type,
            "total_images": len(images),
            "images": images
        }
    
    except frappe.DoesNotExistError:
        return {
            "success": False,
            "error": f"Room type '{room_type}' not found"
        }
    except Exception as e:
        frappe.log_error(f"Error fetching images: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=True)
def get_room_type_inventory(room_type):
    """
    Get standard inventory items for a specific room type.
    
    Args:
        room_type (str): Room Type name
    
    Returns:
        dict: Inventory items list
    """
    try:
        room_type_doc = frappe.get_doc("Hotel Room Type", room_type)
        
        inventory = []
        if hasattr(room_type_doc, 'standard_inventory') and room_type_doc.standard_inventory:
            for inv_item in room_type_doc.standard_inventory:
                inventory.append({
                    "item": inv_item.item,
                    "quantity": inv_item.quantity
                })
        
        return {
            "success": True,
            "room_type": room_type,
            "total_items": len(inventory),
            "inventory": inventory
        }
    
    except frappe.DoesNotExistError:
        return {
            "success": False,
            "error": f"Room type '{room_type}' not found"
        }
    except Exception as e:
        frappe.log_error(f"Error fetching inventory: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist(allow_guest=True)
def get_room_type_basic_info(room_type):
    """
    Get basic information about a room type (no amenities, images, or inventory).
    
    Args:
        room_type (str): Room Type name
    
    Returns:
        dict: Basic room type information
    """
    try:
        room_type_doc = frappe.get_doc("Hotel Room Type", room_type)
        
        basic_info = {
            "name": room_type_doc.name,
            "room_type": room_type_doc.room_type,
            "capacity": room_type_doc.capacity or 0,
            "extra_bed_capacity": room_type_doc.extra_bed_capacity or 0,
            "base_adult": room_type_doc.base_adult or 1,
            "max_adult": room_type_doc.max_adult or 0,
            "base_child": room_type_doc.base_child or 0,
            "max_child": room_type_doc.max_child or 0,
            "is_active": room_type_doc.is_active
        }
        
        return {
            "success": True,
            "room_type": basic_info
        }
    
    except frappe.DoesNotExistError:
        return {
            "success": False,
            "error": f"Room type '{room_type}' not found"
        }
    except Exception as e:
        frappe.log_error(f"Error fetching basic info: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }