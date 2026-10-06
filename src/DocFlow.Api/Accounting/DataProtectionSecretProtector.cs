using DocFlow.Application.Abstractions;
using Microsoft.AspNetCore.DataProtection;

namespace DocFlow.Api.Accounting;

public sealed class DataProtectionSecretProtector
    : ISecretProtector
{
    private readonly IDataProtector _protector;

    public DataProtectionSecretProtector(
        IDataProtectionProvider dataProtectionProvider)
    {
        _protector = dataProtectionProvider.CreateProtector(
            "DocFlow.QuickBooksOnline.OAuthTokens.v1");
    }

    public string Protect(string plaintext)
    {
        if (string.IsNullOrWhiteSpace(plaintext))
            throw new ArgumentException("Secret is required.", nameof(plaintext));

        return _protector.Protect(plaintext);
    }

    public string Unprotect(string protectedValue)
    {
        if (string.IsNullOrWhiteSpace(protectedValue))
        {
            throw new ArgumentException(
                "Protected secret is required.",
                nameof(protectedValue));
        }

        return _protector.Unprotect(protectedValue);
    }
}
