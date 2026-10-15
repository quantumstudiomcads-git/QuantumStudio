export function constantTimeEquals(left, right) {
  if (typeof left !== 'string' || typeof right !== 'string') {
    return false;
  }
  const leftBytes = new TextEncoder().encode(left);
  const rightBytes = new TextEncoder().encode(right);
  if (leftBytes.length !== rightBytes.length) {
    return false;
  }
  try {
    return crypto.subtle.timingSafeEqual(leftBytes, rightBytes);
  } catch {
    let result = 0;
    for (let index = 0; index < leftBytes.length; index += 1) {
      result |= leftBytes[index] ^ rightBytes[index];
    }
    return result === 0;
  }
}

export function getBearerToken(request) {
  const authorization = request.headers.get('Authorization');
  if (!authorization) {
    return null;
  }
  const match = /^Bearer[ \t]+(\S+)$/i.exec(authorization.trim());
  if (!match) {
    return null;
  }
  return match[1].trim() || null;
}
