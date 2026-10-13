import React, {useEffect, useRef, useState} from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import type {AuthUser} from '../lib/auth-client';

export function NavbarAuthControls({
  authenticated,
  loading,
  user,
  onSignOut,
}: {
  authenticated: boolean;
  loading: boolean;
  user?: AuthUser;
  onSignOut: () => void | Promise<void>;
}): React.ReactNode {
  const loginHref = useBaseUrl('/login');
  const betaAccessHref = useBaseUrl('/beta-access');
  const accountHref = useBaseUrl('/account');
  const [menuOpen, setMenuOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);
  const profileButtonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) {
      return undefined;
    }

    const closeOnOutsideClick = (event: PointerEvent) => {
      if (event.target instanceof Node && !profileRef.current?.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('pointerdown', closeOnOutsideClick);
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick);
  }, [menuOpen]);

  if (loading) {
    return <span className="navbar__auth-placeholder" aria-hidden="true" />;
  }

  if (!authenticated) {
    return <a className="navbar__auth-button navbar__auth-button--primary" href={loginHref}>Sign in</a>;
  }

  const closeMenu = (restoreFocus = false) => {
    setMenuOpen(false);
    if (restoreFocus) {
      profileButtonRef.current?.focus();
    }
  };

  const onMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu(true);
      return;
    }

    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const currentIndex = items.indexOf(document.activeElement as HTMLElement);
    let nextIndex: number | null = null;
    if (event.key === 'ArrowDown') {
      nextIndex = (currentIndex + 1) % items.length;
    } else if (event.key === 'ArrowUp') {
      nextIndex = (currentIndex - 1 + items.length) % items.length;
    } else if (event.key === 'Home') {
      nextIndex = 0;
    } else if (event.key === 'End') {
      nextIndex = items.length - 1;
    }
    if (nextIndex !== null && items.length > 0) {
      event.preventDefault();
      items[nextIndex]?.focus();
    }
  };

  return (
    <div className="navbar__auth-controls">
      <a className="navbar__auth-beta-action" href={betaAccessHref}>Beta Access</a>
      <div className="navbar__profile" ref={profileRef}>
        <button
          ref={profileButtonRef}
          type="button"
          className="navbar__profile-button"
          aria-label="Profile menu"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}>
          <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false">
            <circle cx="12" cy="8" r="3.5" />
            <path d="M5.5 20c.4-3.5 2.8-5.5 6.5-5.5s6.1 2 6.5 5.5" />
          </svg>
        </button>
        {menuOpen && (
          <div className="navbar__profile-menu" role="menu" ref={menuRef} onKeyDown={onMenuKeyDown}>
            {(user?.fullName || user?.email) && (
              <div className="navbar__profile-identity">
                {user.fullName && <strong title={user.fullName}>{user.fullName}</strong>}
                {user.email && <span title={user.email}>{user.email}</span>}
              </div>
            )}
            <a role="menuitem" href={accountHref} onClick={() => closeMenu()}>Account</a>
            <button role="menuitem" type="button" onClick={onSignOut}>Sign out</button>
          </div>
        )}
      </div>
    </div>
  );
}
