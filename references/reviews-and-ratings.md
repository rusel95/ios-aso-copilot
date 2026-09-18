# Customer Reviews & Ratings Analysis

App Store ratings and customer reviews are both an algorithmic ranking factor and a direct qualitative mirror of user satisfaction, objections, and core feature value.

---

## 1. CLI Commands for Ratings & Reviews

Run during every audit iteration to capture live user feedback:

```bash
# 1. Check aggregate rating and star histogram across all territories
asc reviews ratings --app "$APP_ID" --all --output json

# 2. List all written customer reviews with full text and reviewer metadata
asc reviews --app "$APP_ID" --output json

# 3. Filter for negative reviews (1-2 stars) to identify bugs or friction
asc reviews --app "$APP_ID" --stars 1,2 --output json

# 4. Check for unreplied reviews that need developer responses
asc reviews --app "$APP_ID" --only-unresponded --output json

# 5. Respond to a customer review
asc reviews respond --review-id "<REVIEW_ID>" --response "Дякуємо за відгук! ..."
```

---

## 2. Incorporating Ratings into ASO & Product Strategy

1. **Volume & Thresholds**:
   * App Store algorithms require a critical mass of ratings in each storefront before displaying an aggregate score (usually ~4-5 ratings in a given territory).
   * Compresso currently has **9 ratings (8 in Ukraine, 1 in Poland)**, all **5.0 stars**.
   * Other storefronts (US, Germany, France, Japan, etc.) show "Not Enough Ratings".
   * Strategy: Prompt timing (governed by the 3-per-year rolling ceiling in `FreeMonthTrackingService`) must trigger right after a successful `cleanup_completed` when user satisfaction is highest.

2. **Qualitative Sentiment & Feature Value**:
   * Analyze what users organically highlight in 5-star reviews:
     * *4K Video Preservation*: ("program zaskoczył mnie jednak możliwością pozostawienia rozdzielczości 4K bez widocznej utraty ostrości").
     * *Side-by-Side Split Screen Preview*: Praised repeatedly as the feature creating confidence before replacement.
     * *On-Device Trust & Space Saving*: ("Now I don't need to buy new iPhone with more storage", "можно оставить видео и фото без удаления").
   * **Action**: Feed these exact user phrases into App Store subtitles, promotional text, and screenshot captions.

3. **Developer Responses**:
   * Apple notifies users when a developer replies to their review.
   * Replying to every review (even positive ones) shows an active, caring developer, increases user loyalty, and encourages new downloaders to leave reviews.
