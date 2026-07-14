import API from "./axios";

/**
 * Permanently delete the authenticated user's account (DPDP Act right to
 * erasure). Irreversible — subscriptions, payments, and watchlist entries
 * are removed server-side too.
 * @returns {Promise<Object>}
 */
export async function deleteAccount() {
    const response = await API.delete("/user/account");
    return response.data;
}
