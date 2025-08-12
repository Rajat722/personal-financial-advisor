package com.db.finance_advisor.config;


import com.plaid.client.ApiClient;
import com.plaid.client.request.PlaidApi;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;


import java.util.HashMap;
import java.util.Map;

@Configuration
public class PlaidConfig {

    @Value("${plaid.client-id}")
    private String clientId;

    @Value("${plaid.secret}")
    private String secret;

    @Value("${plaid.environment}")
    private String environment;

    @Bean
    public PlaidApi plaidApi() {
        String basePath;

        switch (environment.toLowerCase()) {
            case "sandbox":
                basePath = "https://sandbox.plaid.com";
                break;
            case "development":
                basePath = "https://development.plaid.com";
                break;
            case "production":
                basePath = "https://production.plaid.com";
                break;
            default:
                throw new IllegalArgumentException("Invalid Plaid environment: " + environment);
        }

        ApiClient apiClient = new ApiClient();
        apiClient.setBasePath(basePath);

        // Set API Keys as headers
        apiClient.setApiKey("PLAID-CLIENT-ID");
        apiClient.setApiKey("PLAID-SECRET");

        return new PlaidApi(apiClient);
    }
}