const express =
    require("express");

const cors =
    require("cors");

const helmet =
    require("helmet");

const morgan =
    require("morgan");

const authRoutes =
    require(
        "./routes/authRoutes"
    );

const planRoutes =
    require(
        "./routes/planRoutes"
    );

const subscriptionRoutes =
    require(
        "./routes/subscriptionRoutes"
    );

const companyRoutes =
    require(
        "./routes/companyRoutes"
    );

const userCompanyRoutes =
    require(
        "./routes/userCompanyRoutes"
    );

const adminRoutes =
    require(
        "./admin/adminRoutes"
    );

const app =
    express();

app.set("trust proxy", 1);

const paymentRoutes =
    require(
        "./routes/paymentRoutes"
    );

/*
|--------------------------------------------------------------------------
| Middlewares
|--------------------------------------------------------------------------
*/

app.use(
    helmet()
);

// Allowed browser origins; override in production via CORS_ORIGIN
// (comma-separated list, e.g. "https://app.example.com")
const allowedOrigins =

    process.env.CORS_ORIGIN

        ? process.env.CORS_ORIGIN
            .split(",")
            .map((o) => o.trim())

        : [

            "http://localhost:5173",

            "http://localhost:3000",

            "http://127.0.0.1:5173",

            "http://127.0.0.1:3000"

        ];

app.use(
    cors({

        origin: allowedOrigins

    })
);

app.use(
    express.json({

        limit: "100kb"

    })
);

app.use(
    express.urlencoded({

        extended: true,

        limit: "100kb"

    })
);

app.use(
    morgan(

        process.env.NODE_ENV === "production"

            ? "combined"

            : "dev"

    )
);
app.use(
    "/api/payments",
    paymentRoutes
);
/*
|--------------------------------------------------------------------------
| Health Check
|--------------------------------------------------------------------------
*/

app.get(

    "/health",

    (req, res) => {

        res.status(200).json({

            success: true,

            message:
                "Server Running"

        });

    }

);

/*
|--------------------------------------------------------------------------
| Routes
|--------------------------------------------------------------------------
*/

app.use(

    "/api/auth",

    authRoutes

);

app.use(

    "/api/plans",

    planRoutes

);

app.use(

    "/api/subscriptions",

    subscriptionRoutes

);

app.use(

    "/api/companies",

    companyRoutes

);

app.use(

    "/api/user",

    userCompanyRoutes

);

// Pureframe Central Dashboard integration — every route here requires the
// x-central-api-key header (see backend/src/admin/adminAuthMiddleware.js).
// Invisible and inert to regular users and to anyone without that key.
app.use(

    "/api/admin/v1",

    adminRoutes

);

/*
|--------------------------------------------------------------------------
| 404 Handler
|--------------------------------------------------------------------------
*/

app.use(

    (req, res) => {

        res.status(404).json({

            success: false,

            message:
                "Route not found"

        });

    }

);

module.exports =
    app;