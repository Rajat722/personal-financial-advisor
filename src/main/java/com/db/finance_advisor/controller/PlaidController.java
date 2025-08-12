package com.db.finance_advisor.controller;

import com.db.finance_advisor.model.LinkTokenResponse;
import com.db.finance_advisor.model.PublicTokenRequest;
import com.db.finance_advisor.service.PlaidService;
import com.plaid.client.model.InvestmentsHoldingsGetResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/plaid")
public class PlaidController {

    @Autowired
    private PlaidService plaidService;

    @GetMapping("/link-token/{userId}")
    public ResponseEntity<LinkTokenResponse> createLinkToken(@PathVariable String userId) throws Exception {
        return ResponseEntity.ok(plaidService.createLinkToken(userId));
    }

    @PostMapping("/exchange-token")
    public ResponseEntity<String> exchangeToken(@RequestBody PublicTokenRequest request) throws Exception {
        String accessToken = plaidService.exchangePublicToken(request.getPublicToken());
        // Store accessToken securely in DB associated with user
        return ResponseEntity.ok(accessToken);
    }

    @GetMapping("/holdings/{accessToken}")
    public ResponseEntity<InvestmentsHoldingsGetResponse> getHoldings(@PathVariable String accessToken) throws Exception {
        return ResponseEntity.ok(plaidService.getInvestmentHoldings(accessToken));
    }
}

