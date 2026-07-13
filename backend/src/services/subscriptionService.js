const planRepository =
    require(
        "../repositories/planRepository"
    );

const subscriptionRepository =
    require(
        "../repositories/subscriptionRepository"
    );

const FREE_PLAN_ID = 1;
const PREMIUM_PLAN_ID = 2;

/**
 * Compute the end date for a premium subscription that starts at `startDate`.
 *
 * Premium is a one-month plan, billed as a whole calendar month: a plan
 * started on the 14th ends on the 14th of the next month (14 Jul → 14 Aug),
 * not 30 days later.
 */
function premiumEndDate(
    startDate
) {

    const endDate =
        new Date(startDate);

    endDate.setMonth(
        endDate.getMonth() + 1
    );

    return endDate;

}

async function createFreeSubscription(
    userId
) {

    const plan =

        await planRepository
            .findById(
                FREE_PLAN_ID
            );

    const startDate =
        new Date();

    const endDate =
        new Date();

    endDate.setFullYear(

        endDate.getFullYear() + 10

    );

    return subscriptionRepository.create(

        userId,

        plan.id,

        "ACTIVE",

        startDate,

        endDate

    );

}

/**
 * Activate PREMIUM directly, WITHOUT a payment step.
 *
 * TESTING MODE: payment is bypassed so testers can unlock the full
 * premium plan instantly. Mirrors the post-payment activation in
 * paymentController.verifyPayment — deactivate any current subscription,
 * then create a fresh ACTIVE premium subscription for `duration_days`.
 *
 * To re-enable real payments, route premium activation back through the
 * Razorpay verifyPayment flow instead of calling this.
 */
async function createPremiumSubscription(
    userId
) {

    await subscriptionRepository
        .deactivateActiveSubscription(
            userId
        );

    const startDate =
        new Date();

    const endDate =
        premiumEndDate(
            startDate
        );

    return subscriptionRepository.create(

        userId,

        PREMIUM_PLAN_ID,

        "ACTIVE",

        startDate,

        endDate

    );

}

module.exports = {

    createFreeSubscription,

    createPremiumSubscription,

    premiumEndDate

};
