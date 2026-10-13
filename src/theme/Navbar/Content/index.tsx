import React, {type ReactNode, useEffect, useState} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import {ErrorCauseBoundary, ThemeClassNames, useThemeConfig} from '@docusaurus/theme-common';
import {splitNavbarItems, useNavbarMobileSidebar} from '@docusaurus/theme-common/internal';
import NavbarItem, {type Props as NavbarItemConfig} from '@theme/NavbarItem';
import NavbarColorModeToggle from '@theme/Navbar/ColorModeToggle';
import NavbarLogo from '@theme/Navbar/Logo';
import NavbarMobileSidebarToggle from '@theme/Navbar/MobileSidebar/Toggle';
import NavbarSearch from '@theme/Navbar/Search';
import SearchBar from '@theme/SearchBar';
import useBaseUrl from '@docusaurus/useBaseUrl';
import {NavbarAuthControls} from '../../../components/NavbarAuthControls';
import {logout, type AuthSessionResponse} from '../../../lib/auth-client';

function useNavbarItems() {
  return useThemeConfig().navbar.items as NavbarItemConfig[];
}

function NavbarItems({items}: {items: NavbarItemConfig[]}): ReactNode {
  return (
    <>
      {items.map((item, i) => (
        <ErrorCauseBoundary
          key={i}
          onError={(error) =>
            new Error(
              `A theme navbar item failed to render.\nPlease double-check the following navbar item (themeConfig.navbar.items) of your Docusaurus config:\n${JSON.stringify(item, null, 2)}`,
              {cause: error},
            )
          }>
          <NavbarItem {...item} />
        </ErrorCauseBoundary>
      ))}
    </>
  );
}

function NavbarContentLayout({left, right}:{left: ReactNode; right: ReactNode}) {
  return <div className="navbar__inner"><div className={clsx(ThemeClassNames.layout.navbar.containerLeft, 'navbar__items')}>{left}</div><div className={clsx(ThemeClassNames.layout.navbar.containerRight, 'navbar__items navbar__items--right')}>{right}</div></div>;
}

function useAuthSession() {
  const [session, setSession] = useState<AuthSessionResponse>({authenticated: false});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    fetch('/api/auth/session', {credentials: 'same-origin'})
      .then((response) => (response.ok ? response.json() : {authenticated: false}))
      .then((data) => {
        if (active) {
          setSession(data ?? {authenticated: false});
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setSession({authenticated: false});
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  return {session, loading};
}

export default function NavbarContent(): ReactNode {
  const mobileSidebar = useNavbarMobileSidebar();
  const items = useNavbarItems();
  const [leftItems, rightItems] = splitNavbarItems(items);
  const {session, loading: sessionLoading} = useAuthSession();
  const homeUrl = useBaseUrl('/');
  const searchBarItem = items.find((item: any) => item.type === 'search');

  const filteredRightItems = rightItems.filter((item: any) => {
    const label = typeof item.label === 'string' ? item.label.toLowerCase() : '';
    const target = item.to ?? '';
    return !['sign in', 'create account', 'request beta access', 'beta access'].includes(label) && !['/login', '/signup', '/beta-access'].includes(target);
  });

  const signOut = async () => {
    await logout();
    window.location.assign(homeUrl);
  };

  return (
    <>
      <NavbarContentLayout
        left={
          <>
            {!mobileSidebar.disabled && <NavbarMobileSidebarToggle />}
            <NavbarLogo />
            <NavbarItems items={leftItems} />
          </>
        }
        right={
          <>
            <NavbarItems items={filteredRightItems} />
            <NavbarAuthControls
              authenticated={session.authenticated}
              loading={sessionLoading}
              user={session.user}
              onSignOut={signOut}
            />
            <NavbarColorModeToggle />
            {!searchBarItem && (
              <NavbarSearch><SearchBar /></NavbarSearch>
            )}
          </>
        }
      />
    </>
  );
}
