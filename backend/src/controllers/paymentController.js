const crypto =
    require(
        "crypto"
    );

const paymentService =
    require(
        "../services/paymentService"
    );

const paymentRepository =
    require(
        "../repositories/paymentRepository"
    );

const subscriptionRepository =
    require(
        "../repositories/subscriptionRepository"
    );

const planRepository =
    require(
        "../repositories/planRepository"
    );

const subscriptionService =
    require(
        "../services/subscriptionService"
    );

const {
    getCouponDiscount
} = require(
    "../config/coupons"
);

const PREMIUM_PLAN_ID = 2;

async function createOrder(
    req,
    res
) {

    try {

        const plan =

            await planRepository
                .findById(
                    PREMIUM_PLAN_ID
                );

        if (
            !plan
        ) {

            return res
                .status(500)
                .json({

                    success: false,

                    message:
                        "Plan not available"

                });

        }

        // Resolve any coupon to a discount percentage.
        const coupon =
            String(req.body.coupon || "")
                .trim()
                .toUpperCase();

        const discountPercent =
            getCouponDiscount(coupon);

        if (discountPercent === null) {

            return res
                .status(400)
                .json({

                    success: false,

                    message:
                        "Invalid coupon code"

                });

        }

        // 100%-off is a no-payment activation — tell the client to redeem it
        // via the /subscriptions/premium route instead of opening checkout.
        if (discountPercent === 100) {

            return res.json({

                success: true,

                fullDiscount: true

            });

        }

        const amount =
            Math.round(
                Number(plan.price) *
                (100 - discountPercent)
            ) / 100;

        const order =

            await paymentService
                .createOrder(
                    amount
                );

        await paymentRepository
            .create(

                req.user.id,

                amount,

                order.id

            );

        return res.json({

            success: true,

            order,

            discountPercent

        });

    }
    catch (err) {

        console.error(err);

        return res
            .status(500)
            .json({

                success: false,

                message:
                    "Order creation failed"

            });

    }

}

function isSignatureValid(
    orderId,
    paymentId,
    signature
) {

    const generated =

        crypto
            .createHmac(
                "sha256",
                process.env.RAZORPAY_KEY_SECRET
            )
            .update(
                `${orderId}|${paymentId}`
            )
            .digest("hex");

    const expected =
        Buffer.from(generated);

    const received =
        Buffer.from(String(signature));

    if (
        expected.length !==
        received.length
    ) {

        return false;

    }

    return crypto.timingSafeEqual(
        expected,
        received
    );

}

async function verifyPayment(
    req,
    res
) {

    try {

        const {

            razorpay_order_id,

            razorpay_payment_id,

            razorpay_signature

        } = req.body;

        if (
            !razorpay_order_id ||
            !razorpay_payment_id ||
            !razorpay_signature
        ) {

            return res
                .status(400)
                .json({

                    success: false,

                    message:
                        "Missing payment details"

                });

        }

        const payment =

            await paymentRepository
                .findByOrderId(
                    razorpay_order_id
                );

        // The order must exist and belong to the caller
        if (
            !payment ||
            Number(payment.user_id) !==
            Number(req.user.id)
        ) {

            return res
                .status(403)
                .json({

                    success: false,

                    message:
                        "Order not found for this user"

                });

        }

        // Block replaying an already-settled order
        if (
            payment.status === "SUCCESS"
        ) {

            return res
                .status(400)
                .json({

                    success: false,

                    message:
                        "Payment already processed"

                });

        }

        if (
            !isSignatureValid(

                razorpay_order_id,

                razorpay_payment_id,

                razorpay_signature

            )
        ) {

            return res
                .status(400)
                .json({

                    success: false,

                    message:
                        "Invalid payment signature"

                });

        }

        await paymentRepository
            .markPaid(

                razorpay_order_id,

                razorpay_payment_id

            );

        await subscriptionRepository
            .deactivateActiveSubscription(

                req.user.id

            );

        const startDate =
            new Date();

        const endDate =
            subscriptionService.premiumEndDate(
                startDate
            );

        await subscriptionRepository
            .create(

                req.user.id,

                PREMIUM_PLAN_ID,

                "ACTIVE",

                startDate,

                endDate

            );

        return res.json({

            success: true,

            message:
                "Premium subscription activated"

        });

    }
    catch (err) {

        console.error(err);

        return res
            .status(500)
            .json({

                success: false,

                message:
                    "Payment verification failed"

            });

    }

}

module.exports = {

    createOrder,

    verifyPayment

};
