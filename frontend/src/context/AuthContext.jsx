import { createContext, useState, useEffect } from "react";
import { getToken, getUser, setToken, setUser, clearAuth } from "../utils/storage";
import {
    verifyToken as verifyTokenApi,
    loginWithTestCredentials as loginWithTestCredentialsApi,
} from "../api/auth.api";
import { setupInterceptors } from "../api/interceptor";

export const AuthContext = createContext(null);

/**
 * MSG91 widget configuration.
 *
 * The widget is loaded once at app start. Individual pages call
 * window.initSendOTP() with `exposeMethods: true` to prevent the
 * default popup from appearing and instead drive the flow via
 * window.sendOtp / window.retryOtp / window.verifyOtp.
 */
const MSG91_WIDGET_SCRIPT = "https://verify.msg91.com/otp-provider.js";
const MSG91_WIDGET_ID     = import.meta.env.VITE_MSG91_WIDGET_ID;
const MSG91_TOKEN_AUTH    = import.meta.env.VITE_MSG91_TOKEN_AUTH;

export function AuthProvider({ children }) {
    const [user, setUserState] = useState(null);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    // Tracks whether the most recent login/register was for a brand-new
    // account. Read by PublicRoute (see AppRoutes.jsx) to decide whether an
    // authenticated user should land on /whatsapp-welcome or /dashboard.
    // Setting this in the SAME batch as setIsAuthenticated (rather than
    // navigating separately from the calling page) avoids a race where
    // PublicRoute's own redirect-to-dashboard fires before the page's
    // explicit navigate() call, sending new users to the wrong screen.
    const [isNewUser, setIsNewUser] = useState(false);
    const [loading, setLoading] = useState(true);

    // ── Bootstrap ─────────────────────────────────────────────────────────
    useEffect(() => {
        // Register the 401 handler to reset React state on token expiry
        setupInterceptors(() => {
            setUserState(null);
            setIsAuthenticated(false);
        });

        const storedToken = getToken();
        const storedUser  = getUser();

        if (storedToken && storedUser) {
            setUserState(storedUser);
            setIsAuthenticated(true);
        }
        setLoading(false);

        // Load the MSG91 widget script once
        if (!document.querySelector(`script[src="${MSG91_WIDGET_SCRIPT}"]`)) {
            const script    = document.createElement("script");
            script.src      = MSG91_WIDGET_SCRIPT;
            script.async    = true;
            document.body.appendChild(script);
        }
    }, []);

    // ── Helpers ───────────────────────────────────────────────────────────

    /**
     * Wait until window.initSendOTP is available (async script load).
     * @param {number} [attempt=0]
     * @returns {Promise<void>}
     */
    function waitForWidget(attempt = 0) {
        return new Promise((resolve, reject) => {
            if (typeof window.initSendOTP === "function") {
                resolve();
            } else if (attempt < 20) {
                setTimeout(() => waitForWidget(attempt + 1).then(resolve).catch(reject), 300);
            } else {
                reject(new Error("MSG91 widget script failed to load. Please refresh and try again."));
            }
        });
    }

    /**
     * Initialise the MSG91 widget for a given mobile number.
     * Resolves with the MSG91 access-token on success,
     * or rejects with an error on failure.
     *
     * @param {string} mobile - 10-digit mobile number (country code will be prepended)
     * @returns {Promise<string>} MSG91 access-token
     */
    function initMsg91Widget(mobile) {
        return new Promise(async (resolve, reject) => {
            try {
                await waitForWidget();
            } catch (e) {
                return reject(e);
            }

            window.initSendOTP({
                widgetId:      MSG91_WIDGET_ID,
                tokenAuth:     MSG91_TOKEN_AUTH,
                // NOTE: Do NOT pass `identifier` here — MSG91 auto-sends an OTP when
                // identifier is present in the config. The pages call window.sendOtp()
                // explicitly, so passing identifier here causes a duplicate OTP.
                exposeMethods: true,             // prevents default popup; exposes window methods
                success: (data) => {
                    // data.message contains the verified access-token
                    resolve(data.message);
                },
                failure: (error) => {
                    reject(
                        new Error(
                            (typeof error === "string" ? error : error?.message) ||
                            "OTP verification failed"
                        )
                    );
                },
            });
        });
    }

    // ── Auth Actions ──────────────────────────────────────────────────────

    /**
     * Initialise the MSG91 widget and send OTP for login.
     * Returns a promise that resolves with the MSG91 access-token
     * when the user has successfully verified the OTP.
     *
     * After calling this, the page must call window.sendOtp() to trigger delivery.
     *
     * @param {string} mobile - 10-digit mobile number
     * @returns {Promise<string>} MSG91 access-token
     */
    async function login(mobile) {
        return await initMsg91Widget(mobile);
    }

    /**
     * Exchange a verified MSG91 access-token for an internal session JWT.
     * @param {string} mobile
     * @param {string} accessToken - from MSG91 widget success callback
     */
    async function verifyLogin(mobile, accessToken) {
        const data = await verifyTokenApi({ mobile, accessToken });
        if (data.token) {
            setToken(data.token);
            setUser(data.user);
            setUserState(data.user);
            setIsNewUser(!!data.isNewUser);
            setIsAuthenticated(true);
        }
        return data;
    }

    /**
     * Initialise the MSG91 widget and send OTP for registration.
     * @param {string} name   - user's full name (stored after OTP verification)
     * @param {string} mobile - 10-digit mobile number
     * @returns {Promise<string>} MSG91 access-token
     */
    async function register(name, mobile) {
        return await initMsg91Widget(mobile);
    }

    /**
     * Exchange a verified MSG91 access-token for an internal session JWT (registration path).
     * @param {string} name
     * @param {string} mobile
     * @param {string} accessToken - from MSG91 widget success callback
     */
    async function verifyRegister(name, mobile, accessToken) {
        const data = await verifyTokenApi({ name, mobile, accessToken });
        if (data.token) {
            setToken(data.token);
            setUser(data.user);
            setUserState(data.user);
            setIsNewUser(!!data.isNewUser);
            setIsAuthenticated(true);
        }
        return data;
    }

    /**
     * TEMPORARY — Razorpay test-mode login (username/password).
     * Bypasses the MSG91/OTP widget entirely. Only the one reserved test
     * account (created server-side) can succeed here; every successful
     * call is treated as a brand-new account (isNewUser stays true), so
     * the tester is routed through onboarding (/whatsapp-welcome) instead
     * of straight to /dashboard, same as any other first-time user.
     *
     * Remove this function, its Login-page UI, authApi.loginWithTestCredentials,
     * and the backend /auth/login-test route once Razorpay's testing is done.
     *
     * @param {string} username
     * @param {string} password
     */
    async function loginWithTestCredentials(username, password) {
        const data = await loginWithTestCredentialsApi({ username, password });
        if (data.token) {
            setToken(data.token);
            setUser(data.user);
            setUserState(data.user);
            setIsNewUser(!!data.isNewUser);
            setIsAuthenticated(true);
        }
        return data;
    }

    /**
     * Log out user and clear local storage.
     */
    function logout() {
        clearAuth();
        setUserState(null);
        setIsNewUser(false);
        setIsAuthenticated(false);
    }

    const value = {
        user,
        isAuthenticated,
        isNewUser,
        loading,
        login,
        verifyLogin,
        loginWithTestCredentials,
        register,
        verifyRegister,
        logout,
        MSG91_WIDGET_ID,
        MSG91_TOKEN_AUTH,
    };

    return (
        <AuthContext.Provider value={value}>
            {!loading && children}
        </AuthContext.Provider>
    );
}
export default AuthContext;