const userRepository =
    require(
        "../repositories/userRepository"
    );

/**
 * DELETE /api/user/account
 *
 * Self-service account deletion (DPDP Act, 2023 — right to erasure).
 * Permanently deletes the authenticated user's row; subscriptions, payments,
 * and watchlist entries cascade via ON DELETE CASCADE (see migrations
 * 003/004/006). Irreversible.
 */
async function deleteAccount(
    req,
    res
) {

    try {

        const deleted =

            await userRepository
                .deleteById(
                    req.user.id
                );

        if (
            !deleted
        ) {

            return res
                .status(404)
                .json({

                    success: false,

                    message:
                        "Account not found"

                });

        }

        return res.json({

            success: true,

            message:
                "Account deleted"

        });

    }
    catch (err) {

        console.error(err);

        return res
            .status(500)
            .json({

                success: false,

                message:
                    "Failed to delete account"

            });

    }

}

module.exports = {

    deleteAccount

};
