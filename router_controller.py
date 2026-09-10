from librouteros.exceptions import LibRouterosError
import config

def set_gateway_distance(api, route_comment, new_distance):
    """
    Modifies the 'distance' parameter in MikroTik routing based on the route comment.
    Returns:
        True  -> if distance is ACTUALLY changed (real change occurred)
        False -> if no change (already matches), route not found,
                 distance is not safe, or an API error occurs
    """
    if new_distance not in config.SAFE_DISTANCES:
        print(f"[-] SAFETY: distance {new_distance} is not a safe-state {config.SAFE_DISTANCES}. Change aborted.")
        return False

    try:
        routes = list(api.path("ip", "route"))
        target_route = next((r for r in routes if r.get("comment") == route_comment), None)

        if target_route is None:
            print(f"[-] Route with comment '{route_comment}' not found in MikroTik!")
            return False

        route_id = target_route.get(".id")
        current_distance = int(target_route.get("distance", -1))

        # Idempotency check -> DO NOT return True here, because no real change occurred
        if current_distance == new_distance:
            return False

        api.path("ip", "route").update(**{".id": route_id, "distance": str(new_distance)})

        # Audit log to MikroTik (optional, must not fail the failover process if an error occurs)
        try:
            api.path("log").add(
                topics="info",
                message=f"[AI-FAILOVER] {route_comment}: distance {current_distance} -> {new_distance}",
            )
        except LibRouterosError:
            pass

        print(f"⚙️ [MIKROTIK] Route '{route_comment}' distance changed: {current_distance} -> {new_distance}")
        return True

    except LibRouterosError as e:
        print(f"[-] Failed to execute MikroTik command: {e}")
        return False
