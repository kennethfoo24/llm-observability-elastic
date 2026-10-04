INDEX_NAME = "hr-kb"

INDEX_BODY = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "classification": {"type": "keyword"},
            "allowed_roles": {"type": "keyword"},
            "content": {"type": "text", "copy_to": ["content_semantic"]},
            "content_semantic": {"type": "semantic_text", "inference_id": ".elser-2-elastic"},
        }
    }
}
