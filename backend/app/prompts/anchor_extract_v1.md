# Concrete anchor extraction — v1

Extract one to five concrete observations that are explicitly supported by the supplied title, caption, hashtags, OCR, transcript, or visual summary. Each item must include its exact source field, an anchor type, and confidence from 0 to 1.

Never invent an object, color, style, topic, quote, action, or claim. If the content is too sparse, return an empty anchor list and low confidence. Return only the requested JSON schema.
