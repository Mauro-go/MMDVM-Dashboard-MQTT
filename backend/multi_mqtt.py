"""Exclude sibling traffic, including when the first node has a wildcard topic."""
import json
import os
from node_paths import data_file

def accept_event(topic, event):
    if os.environ.get('MMDVM_MULTI_WORKER'):
        import remote_agent
        from mqtt_settings import load
        if topic != load()['topic']:
            return False
        expected = remote_agent.node_id()
        if event.get('node_id') not in (None, expected):
            return False
        return all(not isinstance(value, dict) or value.get('node_id') in (None, expected) for value in event.values())
    registry = data_file('multi') / 'nodes.json'
    try:
        nodes = json.loads(registry.read_text()) if registry.exists() else []
    except (OSError, ValueError):
        # Fail closed while the registry is unreadable.
        return False
    for node in nodes:
        if topic == node['topic'] or topic == node['agent_topic_prefix'] or topic.startswith(node['agent_topic_prefix'] + '/'):
            return False
        if event.get('node_id') == node['node_id']:
            return False
        if any(isinstance(value, dict) and value.get('node_id') == node['node_id'] for value in event.values()):
            return False
    return True
