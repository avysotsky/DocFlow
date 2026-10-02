using System.Net;
using System.Net.Sockets;

namespace DocFlow.Api.Notifications;

public static class WebhookDestinationSecurity
{
    public static bool IsPublicAddress(IPAddress address)
    {
        if (address.IsIPv4MappedToIPv6)
            address = address.MapToIPv4();

        if (IPAddress.IsLoopback(address)
            || address.Equals(IPAddress.Any)
            || address.Equals(IPAddress.IPv6Any)
            || address.Equals(IPAddress.None)
            || address.Equals(IPAddress.IPv6None))
        {
            return false;
        }

        var bytes = address.GetAddressBytes();

        if (address.AddressFamily == AddressFamily.InterNetwork)
        {
            var first = bytes[0];
            var second = bytes[1];
            var third = bytes[2];

            if (first == 0
                || first == 10
                || first == 127
                || first >= 224
                || (first == 100 && second is >= 64 and <= 127)
                || (first == 169 && second == 254)
                || (first == 172 && second is >= 16 and <= 31)
                || (first == 192 && second == 0 && third is 0 or 2)
                || (first == 192 && second == 88 && third == 99)
                || (first == 192 && second == 168)
                || (first == 198 && second is 18 or 19)
                || (first == 198 && second == 51 && third == 100)
                || (first == 203 && second == 0 && third == 113))
            {
                return false;
            }

            return true;
        }

        if (address.AddressFamily == AddressFamily.InterNetworkV6)
        {
            if (address.IsIPv6LinkLocal
                || address.IsIPv6Multicast
                || address.IsIPv6SiteLocal)
            {
                return false;
            }

            if ((bytes[0] & 0xFE) == 0xFC)
                return false;

            if (bytes[0] == 0x20
                && bytes[1] == 0x01
                && bytes[2] == 0x0D
                && bytes[3] == 0xB8)
            {
                return false;
            }

            return true;
        }

        return false;
    }

    public static async ValueTask<Stream> ConnectAsync(
        SocketsHttpConnectionContext context,
        bool allowPrivateNetworks,
        CancellationToken cancellationToken)
    {
        var addresses = await Dns.GetHostAddressesAsync(
            context.DnsEndPoint.Host,
            cancellationToken);

        var candidates = allowPrivateNetworks
            ? addresses
            : addresses.Where(IsPublicAddress).ToArray();

        if (candidates.Length == 0)
        {
            throw new HttpRequestException(
                "Webhook destination did not resolve to an allowed network address.");
        }

        Exception? lastException = null;

        foreach (var address in candidates)
        {
            var socket = new Socket(
                address.AddressFamily,
                SocketType.Stream,
                ProtocolType.Tcp)
            {
                NoDelay = true
            };

            try
            {
                await socket.ConnectAsync(
                    new IPEndPoint(address, context.DnsEndPoint.Port),
                    cancellationToken);

                return new NetworkStream(socket, ownsSocket: true);
            }
            catch (OperationCanceledException)
            {
                socket.Dispose();
                throw;
            }
            catch (SocketException exception)
            {
                socket.Dispose();
                lastException = exception;
            }
        }

        throw new HttpRequestException(
            "Webhook destination could not be reached.",
            lastException);
    }
}
