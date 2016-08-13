-- phpMyAdmin SQL Dump
-- version 4.6.3
-- https://www.phpmyadmin.net/
--
-- Host: mysql
-- Erstellungszeit: 13. Aug 2016 um 15:49
-- Server-Version: 5.5.50
-- PHP-Version: 5.6.24-0+deb8u1

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Datenbank: `monitoring`
--

-- --------------------------------------------------------

--
-- Tabellenstruktur für Tabelle `hosts`
--

CREATE TABLE `hosts` (
  `mac` varchar(17) NOT NULL,
  `tag` varchar(64) NOT NULL,
  `description` text,
  `name` varchar(64) DEFAULT NULL,
  `ipv4_address` varchar(32) DEFAULT NULL,
  `management_url` varchar(128) DEFAULT NULL,
  `group` varchar(16) DEFAULT NULL,
  `deployed` tinyint(1) NOT NULL DEFAULT '1'
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

--
-- Indizes der exportierten Tabellen
--

--
-- Indizes für die Tabelle `hosts`
--
ALTER TABLE `hosts`
  ADD PRIMARY KEY (`mac`),
  ADD UNIQUE KEY `tag` (`tag`),
  ADD UNIQUE KEY `name` (`name`);

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
