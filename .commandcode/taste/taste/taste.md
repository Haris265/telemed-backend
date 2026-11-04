# Taste
- Communicates in Roman Urdu (Latin-script Hindi/Urdu) mixed with English technical terms; expects responses in the same style. Confidence: 0.75
- Wants thorough, detailed work: explicitly asks to "explain in detail" (detail ma samjo) and to "check properly/thoroughly" (thk sa check karna ha) that everything is covered rather than accept a superficial pass. Confidence: 0.68
- Wants review/analysis findings persisted as a self-contained markdown report file in the repo (not just a chat summary), including exact errors/tracebacks, file+line references, severity levels, a list of what's fine, and prioritized next steps. Confidence: 0.6
- Prefers the agent to do fixes hands-on itself (e.g. build/repair things directly) rather than only hand back manual step-by-step instructions. Confidence: 0.55
- Prefers reports/documented findings written in very plain, easy-to-understand language rather than dense or jargon-heavy prose; complains when a report is hard to parse ("samj nahi aa raha kya issue hai"). Confidence: 0.65
- Wants each reported issue paired with a concrete recommended fix (issue + fix), not just a problem description or vague next steps. Confidence: 0.62
