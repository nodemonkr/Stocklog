# StockLog v3.60.1

## Social member profile normalization

- Google, Naver and Kakao social signup now share the same provider-profile locking flow.
- Naver profile mapping: name, gender, birthyear and mobile are stored when returned by Naver.
- Kakao profile mapping: account name, gender, birthyear and phone_number are stored when returned by Kakao.
- Provider-supplied fields are locked in the signup UI and are re-enforced on the backend, so client-side tampering cannot overwrite provider values.
- Missing provider fields remain editable so signup is not blocked when a provider account does not contain the data or the app lacks permission.
- Social OAuth connection test now reports which member fields were actually returned by the provider.
- Kakao consent scopes are not force-added to the authorization URL; production apps must enable/approve the desired consent items in Kakao Developers to avoid invalid_scope failures.
- Provider labels in the signup UI are now dynamic (Google/Naver/Kakao) instead of always saying Google.

## Previous v3.60 changes retained

- Google login/signup button blue styling.
- Admin member withdrawal action with self-admin protection and related-data cleanup.
- Google People API profile field integration.
