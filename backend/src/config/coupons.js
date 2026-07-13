/**
 * Coupon codes for the Premium plan.
 *
 * Percentage coupons apply a discount to the Premium price at Razorpay
 * checkout — the user still pays, just less. The 100%-off coupon is handled
 * separately (no payment) via the /subscriptions/premium activation route.
 *
 * Codes are matched case-insensitively.
 */

// Percentage-discount coupons: CODE -> percent off (0–100).
const PERCENT_COUPONS = {
    SAVE10: 10,
    SAVE20: 20,
    SAVE30: 30
};

/**
 * The 100%-off (no-payment) coupon code. Configurable via env, defaults to
 * PUREFRAME100.
 */
function fullDiscountCode() {

    return String(
        process.env.PREMIUM_COUPON_100 || "PUREFRAME100"
    )
        .trim()
        .toUpperCase();

}

/**
 * Resolve a coupon code to its discount percentage.
 *
 * @param {string} code
 * @returns {number|null} 0 when no code is supplied, 1–100 for a valid coupon,
 *                        or null when the code is unrecognised.
 */
function getCouponDiscount(code) {

    const normalized =
        String(code || "")
            .trim()
            .toUpperCase();

    if (!normalized) {
        return 0;
    }

    if (normalized === fullDiscountCode()) {
        return 100;
    }

    if (
        Object.prototype.hasOwnProperty.call(
            PERCENT_COUPONS,
            normalized
        )
    ) {
        return PERCENT_COUPONS[normalized];
    }

    return null;

}

module.exports = {

    PERCENT_COUPONS,

    fullDiscountCode,

    getCouponDiscount

};
