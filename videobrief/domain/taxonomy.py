"""Single source of truth for content types and native role order."""
CONTENT_MODEL_ROLE_ORDER = {
    "tutorial": ("goal", "prerequisite", "step", "parameter", "pitfall", "result"),
    "interview": ("topic", "speaker_position", "argument", "disagreement", "key_quote", "open_question"),
    "review": ("subject", "criterion", "pro", "con", "tradeoff", "verdict"),
    "lecture": ("central_question", "concept", "relationship", "example", "conclusion", "boundary"),
    "commentary": ("topic", "fact", "opinion", "inference", "controversy", "uncertainty"),
}
CONTENT_MODEL_ROLES = {name: set(roles) for name, roles in CONTENT_MODEL_ROLE_ORDER.items()}
CONTENT_TYPES = set(CONTENT_MODEL_ROLES)
CONTENT_TYPE_LABELS = {
    "tutorial": "操作教程", "interview": "访谈对话", "review": "产品评测",
    "lecture": "知识讲解", "commentary": "观点评论",
}
