# Draft — request for the generator and answer key

*Not sent. To: the author of the Bramblewood Market salty-snacks dataset (contact as listed where the dataset was
published).*

---

**Subject:** Bramblewood salty snacks: request for the generator and answer key

Hi,

I've worked through your Bramblewood salty-snacks case. I built a tested warehouse and answered the five line-review
questions: https://github.com/Akshith597/bramblewood-analytics-engineering

Your README says the generator and answer key are distributed separately. Could you share them? Specifically:

- the generator code and seed, or its parameter file;
- the true values, with their definitions: own-price elasticity by subcategory and for private label, promotion lift
  by mechanic and display, cannibalisation, pantry-loading, forecast bias, and the effect of the FY2025 W27 delist
  test (including any demand-transfer parameter).

I have already frozen every estimate and 90% interval in a tagged commit (`estimates-frozen-v2`) so the key can't
be used to tune them. I'll publish a scorecard comparing estimates to truth, crediting the dataset. If you'd rather
the key itself stay private, I'll publish only the per-parameter comparison, or nothing at all. Your call.

Thanks for building it,
Akshith Reddy
