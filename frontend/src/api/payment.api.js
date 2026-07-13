import API from "./axios";

/**
 * Create Razorpay Order.
 * An optional coupon code applies a percentage discount to the order amount.
 * @param {string} [coupon]
 */
export async function createOrder(coupon) {

    const response =

        await API.post(
            "/payments/create-order",
            { coupon }
        );

    return response.data;

}

/**
 * Verify Razorpay Payment
 */
export async function verifyPayment(
    paymentData
) {

    const response =

        await API.post(

            "/payments/verify",

            paymentData

        );

    return response.data;

}