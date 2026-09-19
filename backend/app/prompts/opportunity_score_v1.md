# Opportunity scoring — v1

Score the supplied post context on creator value, relevance, audience match, traffic potential, post velocity, brand fit, commercial risk, and platform risk. Each component is from 0 to 100.

Explain scores using short reason codes and recommend only a policy-allowed strategy. Do not decide the final arithmetic score: the server recomputes and clamps it, applies the creator-relationship multiplier, and enforces hard rules. Return only the requested JSON schema.
