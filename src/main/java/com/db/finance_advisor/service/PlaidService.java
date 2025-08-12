package com.db.finance_advisor.service;

import com.db.finance_advisor.model.LinkTokenResponse;
import com.plaid.client.request.PlaidApi;
import com.plaid.client.model.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Arrays;

@Service
public class PlaidService {

    @Autowired
    private PlaidApi plaidClient;

    public LinkTokenResponse createLinkToken(String userId) throws Exception {
        LinkTokenCreateRequestUser user = new LinkTokenCreateRequestUser()
                .clientUserId(userId);

        LinkTokenCreateRequest request = new LinkTokenCreateRequest()
                .user(user)
                .clientName("finance_advisor")
                .products(Arrays.asList(Products.INVESTMENTS))
                .countryCodes(Arrays.asList(CountryCode.US))
                .language("en");

        LinkTokenCreateResponse response = plaidClient.linkTokenCreate(request).execute().body();

        return new LinkTokenResponse(response.getLinkToken());
    }

    public String exchangePublicToken(String publicToken) throws Exception {
        ItemPublicTokenExchangeRequest exchangeRequest = new ItemPublicTokenExchangeRequest()
                .publicToken(publicToken);

        ItemPublicTokenExchangeResponse exchangeResponse = plaidClient
                .itemPublicTokenExchange(exchangeRequest).execute().body();

        return exchangeResponse.getAccessToken();
    }

    public InvestmentsHoldingsGetResponse getInvestmentHoldings(String accessToken) throws Exception {
        InvestmentsHoldingsGetRequest request = new InvestmentsHoldingsGetRequest()
                .accessToken(accessToken);

        return plaidClient.investmentsHoldingsGet(request).execute().body();
    }
}
